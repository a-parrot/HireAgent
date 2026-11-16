"""Find matching scoring evidence, without assigning points."""

from app.agents.resume_evaluation_agent.evidence_checks import domain_supported
from app.agents.resume_evaluation_agent.nodes.analyze_resume import document_chunks
from app.agents.resume_evaluation_agent.scoring import require_items, valid_evidence
from app.prompts.prompt_loader import load_prompt, prompt_version
from app.schemas.agents import ScoringEvidence


async def run(runtime, state, *, verify=False):
    rules = await runtime.rules(state["candidate_id"])
    matches = []
    evidence = list(state["analysis"]["evidence"])
    name = state["analysis"]["name"]
    chunks = document_chunks(state["pages"], runtime.config.llm_document_chars)
    for index, chunk in enumerate(chunks):
        if hasattr(runtime, "report_progress"):
            await runtime.report_progress(
                state["candidate_id"],
                "verify_scoring_evidence" if verify else "extract_scoring_evidence",
                index + 1,
                len(chunks),
            )
        result = await runtime.llm.generate(
            load_prompt("scoring_evidence_review" if verify else "scoring_evidence"),
            {
                "rules": {
                    k: rules[k]
                    for k in (
                        "job_name",
                        "responsibilities",
                        "dimensions",
                    )
                    if k in rules
                },
                "pages": chunk,
                "chunk_prefix": f"{'verified_score' if verify else 'score'}{index}_",
            },
            ScoringEvidence,
        )
        require_items(
            result["matches"], "dimension_id", [d["id"] for d in rules["dimensions"]]
        )
        valid = valid_evidence(result["evidence"], chunk)
        name = name or result["name"]
        evidence.extend(valid.values())
        for item in result["matches"]:
            ids = item["evidence_ids"]
            supported = bool(ids) and set(ids) <= valid.keys()
            if item["matched"] and not supported:
                item["reason"] = "未找到可定位的原文证据，本项不得分"
            item["matched"] = item["matched"] and supported
            dimension = next(
                d for d in rules["dimensions"] if d["id"] == item["dimension_id"]
            )
            if item["matched"] and not domain_supported(
                dimension, [valid[key] for key in ids]
            ):
                item["matched"] = False
                item["reason"] = (
                    "引用经历未体现本评分项要求的专业领域，不能用一般项目或管理经历替代"
                )
            item["evidence_ids"] = (
                [key for key in ids if key in valid] if item["matched"] else []
            )
            matches.append(item)
    # Reject colliding evidence IDs rather than silently replacing source quotations.
    valid_evidence(evidence, state["pages"])
    facts = [
        {
            "fact_id": f"score_fact_{i}",
            "type": "scoring_match",
            "description": item["reason"],
            "evidence_ids": item["evidence_ids"],
        }
        for i, item in enumerate(matches)
        if item["matched"]
    ]
    return {
        "scoring_matches": matches,
        "analysis": {
            "name": name,
            "facts": facts,
            "evidence": evidence,
            "missing_fields": [],
        },
    }


def save(candidate, output, config):
    candidate.name = output["analysis"]["name"]
    candidate.evidence = output["analysis"]["evidence"]
    candidate.extracted_facts = output["analysis"]["facts"]
    candidate.prompt_versions = {
        **(candidate.prompt_versions or {}),
        "scoring_evidence": prompt_version("scoring_evidence"),
    }
