"""Synthetic MySQL binary/interrupt/reconnect check; never starts business workflows.

Uses pre-existing checkpoint tables and removes only its UUID-prefixed test thread.
No DDL, candidate data, PDF files, model requests or runtime lock are involved.
"""

import asyncio
import json
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


class SyntheticState(TypedDict, total=False):
    payload: bytes
    decision: str


def graph(saver):
    def pause(state):
        return {"decision": interrupt({"kind": "synthetic-review-only"})}

    builder = StateGraph(SyntheticState)
    builder.add_node("synthetic_review", pause)
    builder.add_edge(START, "synthetic_review")
    builder.add_edge("synthetic_review", END)
    return builder.compile(checkpointer=saver)


async def verify(config):
    db = MySQLClient(
        config
    )  # Installs the compatibility bridge before either connection.
    thread_id = "hireagent-diagnostic-" + uuid4().hex
    uri = db.engine.url.render_as_string(hide_password=False)
    options = {"configurable": {"thread_id": thread_id}}
    payload = bytes(range(256))
    result = {}
    try:
        await db.ping()  # Real, read-only binary parameter round-trip.
        async with AIOMySQLSaver.from_conn_string(uri) as saver:
            value = await graph(saver).ainvoke({"payload": payload}, options)
            assert value.get("__interrupt__"), "synthetic pause was not persisted"
            result["interrupt_persisted"] = True
        # New saver/connection simulates a process restart, not just an in-memory resume.
        async with AIOMySQLSaver.from_conn_string(uri) as saver:
            workflow = graph(saver)
            saved = await workflow.aget_state(options)
            assert saved.values["payload"] == payload
            assert saved.interrupts
            result["binary_roundtrip"] = True
            completed = await workflow.ainvoke(
                Command(resume="synthetic-approved"), options
            )
            assert completed["decision"] == "synthetic-approved"
            assert not (await workflow.aget_state(options)).next
            result["resumed_after_reconnect"] = True
    finally:
        try:
            # This exact ID was generated above; never enumerate or delete user threads.
            async with AIOMySQLSaver.from_conn_string(uri) as saver:
                await saver.adelete_thread(thread_id)
                assert await saver.aget_tuple(options) is None
                result["synthetic_records_removed"] = True
        finally:
            await db.close()
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(verify(Settings()))))
    except Exception as exc:  # noqa: BLE001 - CLI boundary must not expose driver secrets
        # Do not print driver SQL, URI, provider payloads or credentials.
        print(json.dumps({"checkpoint_diagnostic_failed": type(exc).__name__}))
        raise SystemExit(1) from None
