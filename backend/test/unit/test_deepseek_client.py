import json

import httpx
import pytest

from app.clients.llm_client import LLMClient
from app.core.config import Settings
from app.schemas.agents import Verification


@pytest.mark.asyncio
async def test_deepseek_independent_configuration_and_protocol():
    config = Settings(
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key="test-deepseek",
        llm_api_key="unrelated-cloud-key",
    )
    assert config.llm_model == "deepseek-flash"
    assert config.llm_timeout == 300

    def handle(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-deepseek"
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"needs_human_review": false, "review_notes": []}'
                        }
                    }
                ]
            },
        )

    client = LLMClient(config)
    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        assert (await client.generate("JSON", {}, Verification))[
            "needs_human_review"
        ] is False
    finally:
        await client.close()
