import json

import httpx
import pytest
from pydantic import SecretStr

from app.clients.llm_client import LLMClient
from app.core.config import Settings
from app.core.errors import BusinessError
from app.schemas.agents import Verification


@pytest.mark.parametrize("key", ["", "local-test-key"])
@pytest.mark.asyncio
async def test_llama_uses_local_model_settings_and_never_cloud_credentials(key):
    config = Settings(
        _env_file=None,
        llm_provider="llama",
        llm_base_url="https://cloud.invalid/v1",
        llm_model="cloud-model",
        llm_api_key=SecretStr("cloud-private-key"),
        llama_base_url="http://localhost:8080/v1/",
        llama_api_key=SecretStr(key),
        llm_model_name="qwen3.8",
        llama_max_tokens=4096,
    )
    assert config.llm_model == "qwen3.8"
    client = LLMClient(config)

    def handle(request):
        assert str(request.url) == "http://localhost:8080/v1/chat/completions"
        assert request.headers.get("authorization") == (
            "Bearer " + key if key else None
        )
        body = json.loads(request.content)
        assert body["model"] == "qwen3.8"
        assert body["max_tokens"] == 4096
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert "enable_thinking" not in body
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"needs_human_review": false, "review_notes": []}'
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        assert await client.generate("JSON", {}, Verification) == {
            "needs_human_review": False,
            "review_notes": [],
        }
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_llama_missing_local_model_does_not_fall_back_to_cloud_model():
    client = LLMClient(
        Settings(_env_file=None, llm_provider="llama", llm_model="cloud")
    )
    try:
        with pytest.raises(BusinessError, match="LLM_MODEL_NAME"):
            await client.generate("JSON", {}, Verification)
    finally:
        await client.close()
