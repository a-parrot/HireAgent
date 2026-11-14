"""Real model validation, without a business database or external meeting actions."""

import argparse
import asyncio
import json
from pathlib import Path

from app.agents.recruitment_agent.nodes.analysis import (
    CandidateEvaluationAgent,
    EvaluationReviewAgent,
    ResumeAnalysisAgent,
)
from app.agents.recruitment_agent.nodes.summarize_result import summarize
from app.clients.llm_client import LLMClient
from app.core.config import BACKEND_DIR, Settings
from app.services.resume_service.resumes import extract_pdf


async def main(pdf_path):
    config = Settings()
    texts = await asyncio.to_thread(extract_pdf, pdf_path)
    pages = [
        {"file_id": "smoke-file", "page_no": i, "text": t}
        for i, t in enumerate(texts, 1)
    ]
    rules = json.loads(
        (BACKEND_DIR / "app/conf/initial_job.json").read_text(encoding="utf-8")
    )
    llm = LLMClient(config)
    try:
        analysis = await ResumeAnalysisAgent().run(
            llm, rules, pages, config.llm_page_chars
        )
        evaluation = await CandidateEvaluationAgent().run(llm, rules, analysis)
        review = await EvaluationReviewAgent().run(llm, rules, analysis, evaluation)
        summary = summarize(rules, pages, analysis, evaluation, review)
        target = config.storage_dir / "exports" / "model-smoke.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "model": config.llm_model,
                    "analysis": analysis,
                    "evaluation": evaluation,
                    "review": review,
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
                    "pages": len(pages),
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
