"""Reject proven hard-condition failures before any scoring extraction."""

from app.agents.resume_evaluation_agent.decision import combine
from app.agents.resume_evaluation_agent.evidence_checks import explicit_work_years
from app.agents.resume_evaluation_agent.nodes.analyze_resume import (
    document_chunks,
    redact,
)
from app.agents.resume_evaluation_agent.scoring import (
    blocking_conditions,
    condition_leaves,
    require_items,
    valid_evidence,
)
from app.prompts.prompt_loader import load_prompt, prompt_version
from app.schemas.agents import HardConditionScreening


async def read_screening_chunks(runtime, state, rules, pages, leaves, verify):
    output = {"name": None, "hard_conditions": [], "evidence": []}
    if not leaves:
        return output
    groups = document_chunks(pages, runtime.config.llm_document_chars)
    candidates = {leaf["id"]: [] for leaf in leaves}
    evidence = []
    node = "verify_hard_conditions" if verify else "screen_hard_conditions"
    for index, chunk in enumerate(groups):
        if hasattr(runtime, "report_progress"):
            await runtime.report_progress(
                state["candidate_id"], node, index + 1, len(groups)
            )
        part = await runtime.llm.generate(
            load_prompt(
                "hard_condition_review" if verify else "hard_condition_screening"
            ),
            {
                "rules": {
                    k: v
                    for k, v in rules.items()
                    if k
                    in (
                        "job_name",
                        "responsibilities",
                        "requirements",
                        "hard_conditions",
                    )
                },
                "pages": chunk,
            },
            HardConditionScreening,
        )
        require_items(part["hard_conditions"], "condition_id", list(candidates))
        valid = valid_evidence(part["evidence"], chunk)
        # Scope model-generated IDs to this chunk so repeated hard_1 IDs cannot collide.
        names = {key: f"hard_chunk{index}_{key}" for key in valid}
        evidence.extend(
            {**item, "evidence_id": names[key]} for key, item in valid.items()
        )
        output["name"] = output["name"] or part["name"]
        for item in part["hard_conditions"]:
            ids = item["evidence_ids"]
            supported = bool(ids) and set(ids) <= valid.keys()
            item = {**item, "evidence_ids": [names[key] for key in ids if key in names]}
            if item["result"] == "satisfied" and (
                not supported or item.get("basis") in ("not_found", "uncertain")
            ):
                item.update(result="unknown", basis="uncertain", evidence_ids=[])
            candidates[item["condition_id"]].append(item)
    for leaf in leaves:
        items = candidates[leaf["id"]]
        # A non-match in one fragment cannot discard a genuine match later in the PDF.
        found = [item for item in items if item["result"] == "satisfied"]
        negative = [
            item
            for item in items
            if item["result"] == "unsatisfied"
            and item.get("basis") == "evidence"
            and item["evidence_ids"]
        ]
        selected = found[0] if found else negative[0] if negative else items[0]
        output["hard_conditions"].append(
            {
                **selected,
                "evidence_ids": list(
                    dict.fromkeys(
                        key
                        for item in (found or [selected])
                        for key in item["evidence_ids"]
                    )
                ),
            }
        )
    output["evidence"] = evidence
    return output


async def run(runtime, state, *, verify=False):
    rules = await runtime.rules(state["candidate_id"])
    pages = [{**page, "text": redact(page["text"])} for page in state["pages"]]
    leaves = condition_leaves(rules["hard_conditions"])
    result = await read_screening_chunks(runtime, state, rules, pages, leaves, verify)
    conditions = result["hard_conditions"]
    if verify and not result.get("name"):
        result["name"] = state.get("analysis", {}).get("name")
    require_items(conditions, "condition_id", [leaf["id"] for leaf in leaves])
    evidence = valid_evidence(result["evidence"], pages)
    names = {leaf["id"]: leaf["description"] for leaf in leaves}
    for item in conditions:
        item["condition_name"] = names[item["condition_id"]]
        explicit = explicit_work_years(item["condition_name"], pages)
        if explicit:
            source, quote = explicit
            eid = "verified_years_" + item["condition_id"]
            evidence[eid] = {
                "evidence_id": eid,
                "file_id": source["file_id"],
                "block_id": source.get("block_id"),
                "page_no": source.get("page_no"),
                "quote": quote,
            }
            item.update(
                result="satisfied",
                basis="evidence",
                evidence_ids=[eid],
                reason="原文明示“"
                + quote
                + "”，满足本项通用工作年限要求；相关领域经验单独判定。",
            )
        ids = item["evidence_ids"]
        if item.get("basis") == "not_found" and not ids:
            # A complete-document non-match is a business rejection, not fabricated
            # negative evidence. Invalid citations still follow the verification path.
            item["result"] = "unsatisfied"
            item["reason"] = (
                "简历未匹配到满足「" + item["condition_name"] + "」的相关内容。"
            )
        elif item.get("basis") in ("not_found", "uncertain"):
            item["result"] = "unknown"
            if item.get("basis") == "not_found":
                item["reason"] = (
                    "未匹配结论与引用证据不一致，需核实：" + item["condition_name"]
                )
        elif item["result"] != "unknown" and (
            not ids or not set(ids) <= evidence.keys()
        ):
            item["result"] = "unknown"
            item["reason"] = (
                "判定缺少可定位的原文证据，需核实：" + item["condition_name"]
            )
        item["evidence_ids"] = [key for key in ids if key in evidence]
        if verify and item["result"] == "unsatisfied":
            previous = next(
                (
                    c
                    for c in state.get("screening", {}).get("hard_conditions", [])
                    if c["condition_id"] == item["condition_id"]
                ),
                None,
            )
            if previous and previous["result"] == "satisfied":
                prior_evidence = valid_evidence(
                    state.get("analysis", {}).get("evidence", []), pages
                )
                if previous["evidence_ids"] and all(
                    key in prior_evidence for key in previous["evidence_ids"]
                ):
                    item.update(
                        result="unknown",
                        basis="uncertain",
                        reason="原文存在初筛匹配依据，但复核结论不一致，需核实该条件，不能直接判为不满足。",
                    )
                    for key in previous["evidence_ids"]:
                        new_key = "prior_" + key
                        evidence[new_key] = {
                            **prior_evidence[key],
                            "evidence_id": new_key,
                        }
                        item["evidence_ids"].append(new_key)
        # This screening policy requires positive, locatable proof. An unresolved
        # condition is a non-match for this evaluation, not a claim about ability.
        if item["result"] == "unknown":
            item.update(
                result="unsatisfied",
                basis="not_found",
                evidence_ids=[],
                reason="简历未提供能够确认满足「"
                + item["condition_name"]
                + "」的有效原文依据，按硬条件筛选规则判为不满足。",
            )
    status = combine(
        rules["hard_conditions"],
        {item["condition_id"]: item["result"] for item in conditions},
    )
    blockers = blocking_conditions(
        rules["hard_conditions"],
        {item["condition_id"]: item["result"] for item in conditions},
    )
    for item in conditions:
        item["blocking"] = item["condition_id"] in blockers
    notes = (
        [
            f"硬条件未满足：{item['condition_name']}；{item['reason']}"
            for item in conditions
            if item["blocking"]
        ]
        if status == "unsatisfied"
        else []
    )
    screening = {"result": status, "hard_conditions": conditions}
    return {
        "screening": screening,
        "analysis": {
            "name": result["name"],
            "facts": [],
            "evidence": list(evidence.values()),
            "missing_fields": [],
        },
        "evaluation": {
            "hard_conditions": conditions,
            "dimension_scores": [],
            "missing_fields": [],
            "risks": [],
        },
        "summary": {
            "total_score": None,
            "recommendation": "deferred" if status == "unsatisfied" else "needs_review",
            "needs_human_review": status == "unknown",
            "review_notes": notes,
        },
    }


def save(candidate, output, config):
    candidate.name = output["analysis"]["name"]
    candidate.evidence = output["analysis"]["evidence"]
    candidate.extracted_facts = []
    candidate.hard_conditions = output["evaluation"]["hard_conditions"]
    candidate.dimension_scores = []
    candidate.missing_fields = [
        item["condition_name"]
        for item in candidate.hard_conditions
        if item["result"] == "unknown"
    ]
    candidate.risks = []
    candidate.model_id = config.llm_model
    candidate.prompt_versions = {
        **(candidate.prompt_versions or {}),
        "screening": prompt_version("hard_condition_screening"),
    }
    for key, value in output["summary"].items():
        setattr(candidate, key, value)
