import re
from pathlib import Path

from app.schemas.agents import Analysis, Evaluation, Verification

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"


def prompt(name):
    return (PROMPTS / (name + ".md")).read_text(encoding="utf-8")


def redact(text):
    return "\n".join(
        line
        for line in text.splitlines()
        if not re.search(r"性别|婚姻|婚育|民族|出生日期|出生年月|年龄", line)
    )


class ResumeAnalysisAgent:
    async def run(self, llm, rules, pages, max_chars):
        chunks = []
        for page in pages:
            text = redact(page["text"])
            for start in range(0, len(text), max_chars):
                chunks.append({**page, "text": text[start : start + max_chars]})
        output = {"name": None, "facts": [], "evidence": [], "missing_fields": []}
        for index, chunk in enumerate(chunks):
            result = await llm.generate(
                prompt("resume_analysis"),
                {"rules": rules, "pages": [chunk], "chunk_prefix": f"p{index}_"},
                Analysis,
            )
            output["name"] = output["name"] or result["name"]
            for key in ("facts", "evidence", "missing_fields"):
                output[key].extend(result[key])
        return output


class CandidateEvaluationAgent:
    async def run(self, llm, rules, analysis):
        # Chunk-local omissions are not global missing fields; the evaluator sees all facts.
        return await llm.generate(
            prompt("candidate_evaluation"),
            {
                "rules": rules,
                "facts": analysis["facts"],
                "evidence": analysis["evidence"],
            },
            Evaluation,
        )


class EvaluationReviewAgent:
    async def run(self, llm, rules, analysis, evaluation):
        return await llm.generate(
            prompt("evaluation_review"),
            {
                "rules": rules,
                "facts": analysis["facts"],
                "evidence": analysis["evidence"],
                "evaluation": evaluation,
            },
            Verification,
        )
