import json

import httpx
import pytest
from pydantic import SecretStr

from app.clients.llm_client import LLMClient
from app.core.config import Settings
from app.core.errors import BusinessError
from app.schemas.agents import Verification


def client(handler):
    c = LLMClient(
        Settings(
            _env_file=None,
            llm_base_url="https://model.test/v1",
            llm_model="test",
            llm_api_key=SecretStr("test-key-only"),
        )
    )
    return c, httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_model_schema_retry_sends_only_field_errors_not_previous_private_output():
    requests = []

    def handle(req):
        requests.append(json.loads(req.content))
        content = (
            '{"review_notes": "PRIVATE_PREVIOUS_MODEL_TEXT", "needs_human_review": false}'
            if len(requests) == 1
            else '{"review_notes": [], "needs_human_review": false}'
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}]
            },
        )

    c, transport = client(handle)
    await c.http.aclose()
    c.http = httpx.AsyncClient(transport=transport)
    try:
        result = await c.generate("JSON only", {}, Verification)
        assert result == {"review_notes": [], "needs_human_review": False}
        assert len(requests) == 2
        second = json.dumps(requests[1])
        assert "review_notes" in second and "PRIVATE_PREVIOUS_MODEL_TEXT" not in second
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_complete_fenced_json_accepted_without_relaxing_schema():
    c, transport = client(
        lambda req: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"review_notes": [], "needs_human_review": false}\n```'
                        }
                    }
                ]
            },
        )
    )
    await c.http.aclose()
    c.http = httpx.AsyncClient(transport=transport)
    try:
        assert (await c.generate("JSON", {}, Verification))[
            "needs_human_review"
        ] is False
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_structure_retries_are_bounded_and_final_error_is_value_free():
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"review_notes": "PRIVATE_BAD_VALUE", "needs_human_review": false}'
                        }
                    }
                ]
            },
        )

    c, transport = client(handle)
    await c.http.aclose()
    c.http = httpx.AsyncClient(transport=transport)
    try:
        with pytest.raises(BusinessError) as caught:
            await c.generate("JSON", {}, Verification)
        assert len(calls) == 3 and "review_notes" in caught.value.message
        assert "PRIVATE_BAD_VALUE" not in caught.value.message
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_truncated_model_output_has_actionable_error_without_blind_retry():
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"review_notes":'},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    c, transport = client(handle)
    await c.http.aclose()
    c.http = httpx.AsyncClient(transport=transport)
    try:
        with pytest.raises(BusinessError, match="被截断"):
            await c.generate("JSON", {}, Verification)
        assert len(calls) == 1
    finally:
        await c.close()
