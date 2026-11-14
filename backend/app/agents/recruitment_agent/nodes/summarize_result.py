from app.services.job_service.jobs import condition_ids


def combine(node, results):
    if "items" not in node:
        return results.get(node["id"], "unknown")
    values = [combine(child, results) for child in node["items"]]
    if node["operator"] == "all":
        return (
            "unsatisfied"
            if "unsatisfied" in values
            else "unknown"
            if "unknown" in values
            else "satisfied"
        )
    return (
        "satisfied"
        if "satisfied" in values
        else "unknown"
        if "unknown" in values
        else "unsatisfied"
    )


def summarize(rules, pages, analysis, evaluation, review):
    issues = []
    evidence = analysis["evidence"]
    evidence_ids = [e["evidence_id"] for e in evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        issues.append("证据 ID 重复")
    page_map = {(str(p["file_id"]), p["page_no"]): p["text"] for p in pages}

    def normalize(value):
        return "".join(value.split())

    for e in evidence:
        source = page_map.get((str(e["file_id"]), e["page_no"]), "")
        if not normalize(e["quote"]) or normalize(e["quote"]) not in normalize(source):
            issues.append("证据片段无法定位：" + e["evidence_id"])
    known = set(evidence_ids)
    for fact in analysis["facts"]:
        if not fact["evidence_ids"] or not set(fact["evidence_ids"]) <= known:
            issues.append("事实缺少有效证据：" + fact["fact_id"])
    limits = {d["id"]: d["max_score"] for d in rules["dimensions"]}
    scores = evaluation["dimension_scores"]
    valid = {s["dimension_id"] for s in scores} == set(limits) and len(scores) == len(
        limits
    )
    valid = valid and all(
        0 <= s["score"] <= limits.get(s["dimension_id"], -1) for s in scores
    )
    if not valid:
        issues.append("评分维度或分数范围无效")
    conditions = evaluation["hard_conditions"]
    expected = condition_ids(rules["hard_conditions"])
    if len(conditions) != len(expected) or {
        c["condition_id"] for c in conditions
    } != set(expected):
        issues.append("硬条件输出不完整")
    for item in scores + conditions:
        if not item["evidence_ids"] or not set(item["evidence_ids"]) <= known:
            issues.append("条件或分项缺少有效证据")
    total = round(sum(s["score"] for s in scores), 2) if valid else None
    condition = combine(
        rules["hard_conditions"], {c["condition_id"]: c["result"] for c in conditions}
    )
    # Missing or disputed evidence takes precedence, even for a high provisional score.
    needs = bool(
        issues
        or evaluation["missing_fields"]
        or review["needs_human_review"]
        or condition == "unknown"
    )
    recommendation = (
        "needs_review"
        if needs
        else "deferred"
        if condition == "unsatisfied" or total < rules["review_threshold"]
        else "recommended"
        if total >= rules["recommend_threshold"]
        else "needs_review"
    )
    return {
        "total_score": total,
        "recommendation": recommendation,
        "needs_human_review": needs or recommendation == "needs_review",
        "review_notes": review["review_notes"] + issues,
    }
