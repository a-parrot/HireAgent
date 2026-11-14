import asyncio
import json
import re

import httpx
from pydantic import ValidationError

from app.core.errors import BusinessError


class LLMClient:
    """Explicit OpenAI-compatible chat-completions transport; no fake fallback."""

    def __init__(self, config):
        self.config = config
        self.http = httpx.AsyncClient(timeout=config.llm_timeout)

    async def generate(self, prompt, payload, schema):
        config = self.config
        if (
            not config.llm_base_url
            or not config.llm_model
            or not config.llm_api_key.get_secret_value()
        ):
            raise BusinessError(
                "模型未配置：需要 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY", 503
            )
        for attempt in range(3):
            try:
                response = await self.http.post(
                    config.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={
                        "Authorization": "Bearer "
                        + config.llm_api_key.get_secret_value()
                    },
                    json={
                        "model": config.llm_model,
                        "temperature": 0,
                        "max_tokens": config.llm_max_tokens,
                        **(
                            {"enable_thinking": config.llm_enable_thinking}
                            if config.llm_provider == "dashscope"
                            else {}
                        ),
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "system",
                                "content": prompt
                                + "\n只输出 JSON，遵循以下 schema："
                                + json.dumps(
                                    schema.model_json_schema(), ensure_ascii=False
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(payload, ensure_ascii=False),
                            },
                        ],
                    },
                )
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return schema.model_validate_json(content).model_dump()
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                raise BusinessError("模型请求超时或网络失败", 502) from None
            except httpx.HTTPStatusError as exc:
                code = ""
                try:
                    raw = exc.response.json().get("error", {}).get("code", "")
                    if isinstance(raw, str) and re.fullmatch(
                        r"[A-Za-z0-9_.-]{1,100}", raw
                    ):
                        code = " (" + raw + ")"
                except (ValueError, AttributeError):
                    pass
                raise BusinessError(
                    f"模型服务返回 HTTP {exc.response.status_code}{code}", 502
                ) from None
            except (ValidationError, ValueError, KeyError, IndexError, TypeError):
                raise BusinessError("模型输出无法解析为约定结构", 502) from None

    async def close(self):
        await self.http.aclose()
