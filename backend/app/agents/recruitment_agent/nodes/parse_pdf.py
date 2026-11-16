"""Wait for the import workflow, then hand the full document to evaluation."""

import asyncio

from app.models.mysql.entities import Candidate
from app.repositories.common import require
from app.services.resume_service.resumes import parse_pdf


async def run(runtime, state):
    async with runtime.db.session() as session:
        candidate = await require(session, Candidate, state["candidate_id"])
        file_id = candidate.file_id
    async with runtime.file_locks.setdefault(file_id, asyncio.Lock()):
        if runtime.imports is not None:
            await runtime.imports.ensure_parsed(file_id)
        return {"pages": await parse_pdf(runtime.db, runtime.config, file_id)}
