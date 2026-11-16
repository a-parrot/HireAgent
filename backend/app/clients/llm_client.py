import asyncio
import json
import re
from time import perf_counter

import httpx
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.core.errors import BusinessError
from app.core.logging import logger, traced
from app.prompts.prompt_loader import render_messages


class LLMClient:
    """Explicit OpenAI-compatible chat-completions transport; no fake fallback."""

    def __init__(self, config):
        self.config = config
        self.http = httpx.AsyncClient(timeout=config.llm_timeout)

    @traced("model.call")
    async def generate(self, prompt, payload, schema):
        config = self.config
        if isinstance(prompt, ChatPromptTemplate):
            try:
                messages = render_messages(prompt, payload, schema)
            except ValueError:
                raise BusinessError(
                    "提示词模板缺少必要输入，请检查节点参数", 500
                ) from None
        else:
            # Keep simple diagnostic scripts compatible with string prompts.
            messages = [
                {
                    "role": "system",
                    "content": prompt
                    + "\n只输出 JSON，遵循以下 schema："
                    + json.dumps(schema.model_json_schema(), ensure_ascii=False),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        key = config.llm_api_key.get_secret_value()
        if (
            not config.llm_base_url
            or not config.llm_model
            or (not key and config.llm_provider != "llama")
        ):
            raise BusinessError(
                "本地模型未配置：需要 LLAMA_BASE_URL、LLM_MODEL_NAME（启用鉴权时填写 LLAMA_API_KEY）"
                if config.llm_provider == "llama"
                else "模型未配置：需要 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY",
                503,
            )
        for attempt in range(3):
            started = perf_counter()
            log = logger.bind(
                model=config.llm_model,
                provider=config.llm_provider,
                schema=schema.__name__,
                attempt=attempt + 1,
            )
            log.bind(
                input_chars=sum(len(message["content"]) for message in messages)
            ).info("model.request")
            try:
                response = await self.http.post(
                    config.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + key} if key else {},
                    json={
                        "model": config.llm_model,
                        "temperature": config.llm_temperature,
                        "max_tokens": config.llm_max_tokens,
                        **(
                            {"enable_thinking": config.llm_enable_thinking}
                            if config.llm_provider == "dashscope"
                            else {
                                "chat_template_kwargs": {
                                    "enable_thinking": config.llm_enable_thinking
                                }
                            }
                            if config.llm_provider == "llama"
                            else {
                                "thinking": {
                                    "type": "enabled"
                                    if config.llm_enable_thinking
                                    else "disabled"
                                }
                            }
                            if config.llm_provider == "deepseek"
                            else {}
                        ),
                        "response_format": {"type": "json_object"},
                        "messages": messages,
                    },
                )
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    log.bind(
                        http_status=response.status_code, delay_seconds=2**attempt
                    ).warning("model.retry_http")
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                choice = response.json()["choices"][0]
                usage = response.json().get("usage") or {}
                log.bind(
                    http_status=response.status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    usage={
                        key: value
                        for key, value in usage.items()
                        if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                        and type(value) is int
                    },
                ).info("model.response")
                if choice.get("finish_reason") == "length":
                    raise BusinessError(
                        "模型输出被截断，请增加 LLM_MAX_TOKENS 或缩短单次分析正文", 502
                    )
                content = choice["message"]["content"]
                if not isinstance(content, str):
                    raise BusinessError("模型服务未返回可用的 JSON 文本", 502)
                # Accept an otherwise complete JSON document wrapped in a code fence.
                wrapped = re.fullmatch(
                    r"\s*```(?:json)?\s*\n?(.*?)\n?```\s*",
                    content,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                content = wrapped.group(1) if wrapped else content
                try:
                    result = schema.model_validate_json(content).model_dump()
                    log.info("model.schema_validated")
                    return result
                except ValidationError as exc:
                    issues = []
                    for error in exc.errors(include_input=False, include_context=False)[
                        :5
                    ]:
                        path = (
                            ".".join(
                                str(v)
                                for v in error["loc"]
                                if isinstance(v, int)
                                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(v))
                            )
                            or "json"
                        )
                        issues.append({"path": path, "type": error["type"]})
                    if attempt < 2:
                        log.bind(validation_issues=issues).warning("model.retry_schema")
                        # Retry with schema locations only. Do not echo raw model values,
                        # which can contain personal data or injected instructions.
                        messages = [
                            *messages[:2],
                            {
                                "role": "user",
                                "content": "上次输出未通过结构校验，请重新输出完整 JSON，遵守字段类型和证据要求，不编造信息。格式错误："
                                + json.dumps(issues, ensure_ascii=False),
                            },
                        ]
                        continue
                    fields = ", ".join(f"{e['path']}:{e['type']}" for e in issues[:3])
                    raise BusinessError(
                        "模型输出连续三次不符合约定结构（" + fields + "）", 502
                    ) from None
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    log.bind(delay_seconds=2**attempt).warning("model.retry_network")
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
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                raise BusinessError(
                    "模型服务响应格式不正确，请检查兼容接口配置", 502
                ) from None

    async def close(self):
        await self.http.aclose()
