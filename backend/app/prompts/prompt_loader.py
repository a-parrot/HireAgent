"""按功能加载模板，并将固定职责与动态业务输入分成两条消息。"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

PROMPT_DIR = Path(__file__).resolve().parent
INPUT_SEPARATOR = "--- INPUT ---"
PROMPT_NAMES = (
    "resume_analysis",
    "candidate_evaluation",
    "evaluation_review",
    "hard_condition_screening",
    "scoring_evidence",
    "hard_condition_review",
    "scoring_evidence_review",
)


@lru_cache(maxsize=7)
def load_prompt(name: str) -> ChatPromptTemplate:
    if name not in PROMPT_NAMES:
        raise ValueError(f"未知提示词功能：{name}")
    content = (PROMPT_DIR / f"{name}.prompt").read_text(encoding="utf-8")
    system, user = content.split(INPUT_SEPARATOR, 1)
    return ChatPromptTemplate.from_messages(
        [("system", system.strip()), ("human", user.strip())]
    )


def render_messages(template: ChatPromptTemplate, payload: dict, schema) -> list[dict]:
    variables = {
        key: json.dumps(value, ensure_ascii=False) for key, value in payload.items()
    }
    variables["output_schema"] = json.dumps(
        schema.model_json_schema(), ensure_ascii=False
    )
    missing = set(template.input_variables) - variables.keys()
    if missing:
        raise ValueError("提示词缺少变量：" + ", ".join(sorted(missing)))
    return [
        {
            "role": "system" if message.type == "system" else "user",
            "content": message.content,
        }
        for message in template.format_messages(**variables)
    ]


@lru_cache(maxsize=7)
def prompt_version(name: str) -> str:
    # The cached template, not a later edit to the file, is the version in use.
    template = load_prompt(name)
    source = "\n".join(message.prompt.template for message in template.messages)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
