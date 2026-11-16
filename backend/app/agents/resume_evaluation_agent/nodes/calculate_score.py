"""Deterministic all-or-zero points per configured scoring item."""

from app.core.errors import BusinessError


async def run(runtime, state):
    rules = await runtime.rules(state["candidate_id"])
    dimensions = rules["dimensions"]
    if round(sum(float(d["max_score"]) for d in dimensions), 2) != 100:
        raise BusinessError("岗位评分项的分值合计必须为 100 分")
    scores = []
    for dim in dimensions:
        unmatched_reasons = [
            m["reason"]
            for m in state["scoring_matches"]
            if m["dimension_id"] == dim["id"] and not m["matched"] and m.get("reason")
        ]
        matches = [
            m
            for m in state["scoring_matches"]
            if m["dimension_id"] == dim["id"] and m["matched"]
        ]
        scores.append(
            {
                "dimension_id": dim["id"],
                "dimension_name": dim["name"],
                "max_score": dim["max_score"],
                "matched": bool(matches),
                "score": dim["max_score"] if matches else 0,
                "reason": "；".join(dict.fromkeys(m["reason"] for m in matches))
                if matches
                else "不满足该评分项："
                + (
                    "；".join(dict.fromkeys(unmatched_reasons))
                    or "简历未匹配到相关经历"
                )
                + "；本项计 0 分",
                "evidence_ids": list(
                    dict.fromkeys(e for m in matches for e in m["evidence_ids"])
                ),
            }
        )
    total = round(sum(float(s["score"]) for s in scores), 2)
    unknown = state["screening"]["result"] == "unknown"
    recommendation = (
        "needs_review"
        if unknown
        else "recommended"
        if total >= rules["recommend_threshold"]
        else "needs_review"
        if total >= rules["review_threshold"]
        else "deferred"
    )
    missing = (
        [
            c["condition_name"]
            for c in state["screening"]["hard_conditions"]
            if c["result"] == "unknown"
        ]
        if unknown
        else []
    )
    return {
        "evaluation": {
            "hard_conditions": state["screening"]["hard_conditions"],
            "dimension_scores": scores,
            "risks": [],
            "missing_fields": missing,
        },
        "summary": {
            "total_score": total,
            "recommendation": recommendation,
            "needs_human_review": recommendation == "needs_review",
            "review_notes": ["硬条件待核实：" + name for name in missing],
        },
    }


def save(candidate, output, config):
    for key, value in output["evaluation"].items():
        setattr(candidate, key, value)
    for key, value in output["summary"].items():
        setattr(candidate, key, value)
    if candidate.needs_human_review:
        candidate.current_node = "human_review"
