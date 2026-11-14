from uuid import uuid4

from app.core.errors import BusinessError
from app.models.mysql.entities import Job, JobRuleVersion
from app.repositories.common import serialize
from app.repositories.job_repo import jobs as repo


def validate_rules(rules):
    if not isinstance(rules, dict):
        raise BusinessError("请配置评分规则")
    dims = rules.get("dimensions", [])
    if not isinstance(dims, list) or any(not isinstance(d, dict) for d in dims):
        raise BusinessError("评分维度必须为对象列表")
    ids = [d.get("id") for d in dims]
    if (
        not dims
        or any(not isinstance(i, str) or not i.strip() for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise BusinessError("评分维度 ID 必须非空且唯一")
    for dim in dims:
        if (
            not dim.get("name")
            or not dim.get("criteria")
            or type(dim.get("max_score")) is not int
            or dim["max_score"] <= 0
        ):
            raise BusinessError("维度名称、评分标准及正整数上限必填")
    if sum(d["max_score"] for d in dims) != 100:
        raise BusinessError("维度上限合计必须为 100")
    low, high = rules.get("review_threshold"), rules.get("recommend_threshold")
    if (
        type(low) not in (int, float)
        or type(high) not in (int, float)
        or not 0 <= low < high <= 100
    ):
        raise BusinessError("阈值必须满足 0≤复核阈值<推荐阈值≤100")
    sort = rules.get("sort_priority", [])
    if not isinstance(sort, list) or any(not isinstance(item, dict) for item in sort):
        raise BusinessError("排序配置必须为对象列表")
    fields = [item.get("field") for item in sort]
    if (
        not fields
        or fields[0] != "total_score"
        or len(set(fields)) != len(fields)
        or any(f not in ids + ["total_score"] for f in fields)
    ):
        raise BusinessError("排序必须总分优先且引用有效不重复维度")
    if any(item.get("direction") != "desc" for item in sort):
        raise BusinessError("评分排序仅支持降序")

    def condition(node):
        if not isinstance(node, dict):
            raise BusinessError("硬条件格式无效")
        if "items" in node:
            if node.get("operator") not in ("all", "any") or not node["items"]:
                raise BusinessError("硬条件仅支持非空 all/any 组合")
            for child in node["items"]:
                condition(child)
        elif not node.get("id") or not node.get("description"):
            raise BusinessError("硬条件必须包含 ID 与说明")

    condition(rules.get("hard_conditions"))
    leaves = condition_ids(rules["hard_conditions"])
    if len(set(leaves)) != len(leaves):
        raise BusinessError("硬条件叶子 ID 重复")
    # This is a basic guard, not a claim of exhaustive discrimination detection.
    import json

    text = json.dumps([dims, rules["hard_conditions"]], ensure_ascii=False)
    if any(word in text for word in ("年龄", "性别", "婚育", "民族", "种族")):
        raise BusinessError("不能使用受保护属性评分")
    return rules


def condition_ids(node):
    if "items" in node:
        return [i for child in node["items"] for i in condition_ids(child)]
    return [node["id"]]


async def list_jobs(db, page, page_size):
    async with db.session() as session:
        rows, count = await repo.page_jobs(session, page, page_size)
        return {"items": [serialize(r) for r in rows], "total": count}


async def create_job(db, data, code=None):
    async with db.session() as session:
        job = Job(code=code or uuid4().hex, **data.model_dump())
        session.add(job)
        await session.flush()
        return serialize(job)


async def detail(db, job_id):
    async with db.session() as session:
        job = await repo.get_job(session, job_id)
        result = serialize(job)
        versions = await repo.versions(session, job_id)
        result["versions"] = [serialize(v) for v in versions]
        return result


async def patch_job(db, job_id, data):
    async with db.session() as session:
        job = await repo.get_job(session, job_id, lock=True)
        if job.draft_version != data.draft_version:
            raise BusinessError("草稿已更新，请刷新", 409)
        for key, value in data.model_dump(
            exclude_unset=True, exclude={"draft_version"}
        ).items():
            if key == "name" and value is None:
                raise BusinessError("岗位名称不能为空")
            setattr(job, key, value)
        job.draft_version += 1
        await session.flush()
        return serialize(job)


async def publish(db, job_id, data):
    async with db.session() as session:
        job = await repo.get_job(session, job_id, lock=True)
        if job.status != "active" or job.draft_version != data.draft_version:
            raise BusinessError("岗位已停用或草稿版本已变化", 409)
        rules = validate_rules(job.draft_rules)
        latest = await repo.latest_version_number(session, job_id)
        version = JobRuleVersion(
            job_id=job_id,
            version_no=(latest or 0) + 1,
            rule_snapshot={
                **rules,
                "job_name": job.name,
                "responsibilities": job.responsibilities,
                "requirements": job.requirements,
            },
            published_by=data.operator_name,
        )
        session.add(version)
        job.draft_version += 1
        await session.flush()
        return serialize(version)


async def disable(db, job_id):
    async with db.session() as session:
        job = await repo.get_job(session, job_id, lock=True)
        job.status = "disabled"
        await session.flush()
        return serialize(job)
