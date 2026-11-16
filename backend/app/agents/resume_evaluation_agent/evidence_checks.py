"""Narrow source-backed checks; never infer experience from age or a job title."""

import re


def explicit_work_years(condition, pages):
    # Only prove a generic work-experience alternative. A related-industry
    # requirement or an AND clause must still be judged independently.
    requirement = re.search(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*年以上(?:的)?工作经验", condition
    )
    if not requirement or re.search(r"且|并且|同时|以及", condition):
        return None
    if re.search(
        r"相关|领域|行业|钢构|MiC|海外", condition[: requirement.start()], re.IGNORECASE
    ):
        return None
    years = []
    for page in pages:
        for match in re.finditer(
            r"(?<![\d.])(\d+(?:\.\d+)?)\s*年(?:的)?工作经验", page["text"]
        ):
            prefix = page["text"][max(0, match.start() - 12) : match.start()]
            if re.search(r"未|无|没有|不满|不足|要求|期望|招聘|需具备", prefix):
                continue
            years.append((float(match[1]), page, match.group()))
    if years and all(value >= float(requirement[1]) for value, _, _ in years):
        return years[0][1], years[0][2]
    return None


def domain_supported(dimension, evidence):
    """Specialist criteria require a domain anchor in their cited evidence."""
    criterion = dimension.get("name", "") + " " + dimension.get("criteria", "")
    quotes = "\n".join(e["quote"] for e in evidence)
    if "钢结构" in criterion or "钢构" in criterion:
        steel = re.search(
            r"钢结构|钢构|structural\s+steel|steel[-\s]+(?:structure|construction|frame)",
            quotes,
            re.IGNORECASE,
        )
        # MiC / modular is an explicit alternative only where the rule says so.
        modular = re.search(
            r"\bMiC\b|模块化|模組化|modular|prefabricat", quotes, re.IGNORECASE
        )
        alternative = re.search(r"MiC|模块化", criterion, re.IGNORECASE)
        return bool(steel or (alternative and modular))
    return True
