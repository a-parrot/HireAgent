"""手动测试真实模型：uv run python test/test_llm_client.py。"""

import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.llm_client import LLMClient
from app.core.config import Settings
from app.core.errors import BusinessError
from test.live_checks import require_live_check


class ConnectivityResult(BaseModel):
    answer: str = Field(min_length=1)


async def check_llm() -> int:
    try:
        config = Settings().model_copy(update={"llm_max_tokens": 128})
    except ValueError:
        print("[失败] .env 配置格式不正确，请检查模型配置。")
        return 1

    print(f"测试模型：{config.llm_model or '未配置'}（{config.llm_provider}）")
    question = "请用中文一句话介绍你可以如何帮助招聘人员分析简历。"
    print(f"测试问题：{question}")
    print("不读取或发送任何真实简历。")
    client = LLMClient(config)
    try:
        result = await client.generate(
            '请回答用户的问题，只输出 JSON，格式为 {"answer":"你的实际回答"}。',
            {"question": question},
            ConnectivityResult,
        )
        print("[通过] 模型 API 和结构化输出正常。")
        print(f"模型回答：{result['answer']}")
        return 0
    except BusinessError as exc:
        print(f"[失败] {exc.message}")
        print(
            "本地模型检查 LLAMA_BASE_URL、LLM_MODEL_NAME、LLAMA_API_KEY；云模型检查 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY。"
        )
        return 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_llm_connection(request, capsys):
    require_live_check(request, __file__, "RUN_LLM_TESTS")
    with capsys.disabled():
        code = await check_llm()
    assert code == 0, "LLM 测试失败，请查看上方的模型错误提示"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check_llm()))
