"""Versioned hard-condition-first flow; scores are assigned by code."""

from app.agents.resume_evaluation_agent.decision import combine
from app.core.errors import BusinessError

FLOW_VERSION = "hard_conditions_verified_v2"
LEGACY_FLOW_VERSION = "hard_conditions_first_v1"


def new_snapshot(rules):
    return {**rules, "evaluation_flow": FLOW_VERSION}


def condition_leaves(node):
    if "items" not in node:
        return [node]
    return [leaf for child in node["items"] for leaf in condition_leaves(child)]


def blocking_conditions(node, results):
    if combine(node, results) != "unsatisfied":
        return set()
    if "items" not in node:
        return {node["id"]}
    return {
        key for child in node["items"] for key in blocking_conditions(child, results)
    }


def valid_evidence(evidence, pages):
    def normalize(value):
        return "".join(value.split())

    result = {}
    seen = set()
    for item in evidence:
        key = item["evidence_id"]
        if key in seen:
            raise BusinessError("模型返回重复证据 ID，请重试评估", 502)
        seen.add(key)
        for source in pages:
            same = str(item["file_id"]) == str(source["file_id"])
            same = same and (
                item.get("block_id") == source.get("block_id")
                if item.get("block_id")
                else item.get("page_no") is not None
                and item.get("page_no") == source.get("page_no")
            )
            quote = normalize(item["quote"])
            if same and quote and quote in normalize(source["text"]):
                result[key] = item
                break
    return result


def require_items(items, field, expected):
    ids = [item[field] for item in items]
    if len(ids) != len(expected) or set(ids) != set(expected):
        raise BusinessError("模型返回的规则项不完整或重复，请重试评估", 502)
