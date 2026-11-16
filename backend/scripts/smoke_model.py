"""Real model validation, without a business database or external meeting actions."""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app.agents.resume_evaluation_agent.nodes import (
    calculate_score,
    extract_scoring_evidence,
    screen_hard_conditions,
    verify_hard_conditions,
    verify_scoring_evidence,
)
from app.agents.resume_evaluation_agent.scoring import new_snapshot
from app.clients.llm_client import LLMClient
from app.clients.pdf_client import PDFClient
from app.core.config import BACKEND_DIR, Settings


async def main(pdf_path):
    config = Settings()
    text = await PDFClient().extract(pdf_path)
    pages = [
        {"file_id": "smoke-file", "block_id": "document", "page_no": None, "text": text}
    ]
    rules = json.loads(
        (BACKEND_DIR / "app/conf/initial_job.json").read_text(encoding="utf-8")
    )
    llm = LLMClient(config)
    try:

        async def get_rules(candidate_id):
            return new_snapshot(rules)

        runtime = SimpleNamespace(llm=llm, config=config, rules=get_rules)
        state = {"candidate_id": 0, "pages": pages}
        state.update(await screen_hard_conditions.run(runtime, state))
        state.update(await verify_hard_conditions.run(runtime, state))
        if state["screening"]["result"] != "unsatisfied":
            state.update(await extract_scoring_evidence.run(runtime, state))
            state.update(await verify_scoring_evidence.run(runtime, state))
            state.update(await calculate_score.run(runtime, state))
        analysis, evaluation, summary = (
            state["analysis"],
            state["evaluation"],
            state["summary"],
        )
        target = config.storage_dir / "exports" / "model-smoke.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "model": config.llm_model,
                    "analysis": analysis,
                    "evaluation": evaluation,
                    "screening": state["screening"],
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "model": config.llm_model,
                    "source_documents": len(pages),
                    "facts": len(analysis["facts"]),
                    "evidence": len(analysis["evidence"]),
                    "total_score": summary["total_score"],
                    "recommendation": summary["recommendation"],
                    "review_issues": len(summary["review_notes"]),
                    "output": "storage/exports/model-smoke.json",
                },
                ensure_ascii=False,
            )
        )
    finally:
        await llm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.pdf))
