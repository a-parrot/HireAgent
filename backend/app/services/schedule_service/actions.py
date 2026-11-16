import asyncio

from sqlalchemy import select

from app.core.errors import BusinessError
from app.core.logging import logger, traced
from app.models.mysql.entities import (
    ActionRecord,
    Candidate,
    Event,
    Reservation,
    Slot,
    utcnow,
)
from app.repositories.common import require, serialize


class ActionService:
    def __init__(self, db, meeting, notification, timeout=30):
        self.db, self.meeting, self.notification = db, meeting, notification
        self.timeout = timeout
        self.locks = {}

    async def audit(self, session, reservation_id, action, status):
        reservation = await require(session, Reservation, reservation_id)
        log = logger.bind(
            reservation_id=reservation_id,
            candidate_id=reservation.candidate_id,
            action=action,
            action_status=status,
        )
        log.log(
            "WARNING" if status in ("failed", "uncertain") else "INFO",
            "external.action_state",
        )
        session.add(
            Event(
                batch_id=reservation.batch_id,
                candidate_id=reservation.candidate_id,
                node_name="create_meeting"
                if action == "meeting"
                else "send_notification",
                event_type=f"{action}_{status}",
                level="error" if status in ("failed", "uncertain") else "info",
                message=f"{action}: {status}",
            )
        )

    async def preview(self, reservation_id):
        async with self.db.session() as session:
            reservation = await require(session, Reservation, reservation_id)
            candidate = await require(session, Candidate, reservation.candidate_id)
            slot = await require(session, Slot, reservation.slot_id)
            records = (
                await session.scalars(
                    select(ActionRecord).where(
                        ActionRecord.reservation_id == reservation_id
                    )
                )
            ).all()
            return {
                "reservation": serialize(reservation),
                "candidate_name": candidate.name,
                "slot": serialize(slot),
                "actions": [serialize(r) for r in records],
                "meeting_configured": self.meeting.configured,
                "notification_configured": self.notification.configured,
            }

    async def edit_preview(self, reservation_id, data):
        async with (
            self.locks.setdefault(reservation_id, asyncio.Lock()),
            self.db.session() as session,
        ):
            reservation = await require(session, Reservation, reservation_id, lock=True)
            if reservation.preview_version != data.preview_version:
                raise BusinessError("预览版本过期", 409)
            actions = (
                await session.scalars(
                    select(ActionRecord).where(
                        ActionRecord.reservation_id == reservation_id
                    )
                )
            ).all()
            if any(a.status in ("running", "succeeded", "uncertain") for a in actions):
                raise BusinessError("动作已执行或结果待核实，不能修改预览", 409)
            candidate = await require(session, Candidate, reservation.candidate_id)
            slot = await require(session, Slot, reservation.slot_id)
            reservation.preview_version += 1
            reservation.action_preview = {
                "candidate_name": candidate.name,
                "recipient": data.recipient,
                "content": data.content,
                "starts_at": slot.starts_at.isoformat() + "Z",
                "ends_at": slot.ends_at.isoformat() + "Z",
                "timezone": slot.timezone,
                "interviewer": slot.interviewer,
            }
            reservation.approved_preview_version, reservation.approved_preview = (
                None,
                None,
            )
            reservation.approved_by, reservation.approved_at = None, None
            await session.flush()
            return serialize(reservation)

    @traced("external.approve", agent="interview", id_arg="reservation_id")
    async def approve(self, reservation_id, data):
        async with (
            self.locks.setdefault(reservation_id, asyncio.Lock()),
            self.db.session() as session,
        ):
            reservation = await require(session, Reservation, reservation_id, lock=True)
            candidate = await require(session, Candidate, reservation.candidate_id)
            if (
                candidate.review_status != "approved"
                or not reservation.action_preview
                or reservation.preview_version != data.preview_version
            ):
                raise BusinessError("缺少有效候选人批准或预览版本已变化", 409)
            reservation.approved_preview_version = data.preview_version
            reservation.approved_preview = reservation.action_preview
            reservation.approved_by, reservation.approved_at = (
                data.operator_name,
                utcnow(),
            )
            session.add(
                Event(
                    batch_id=reservation.batch_id,
                    candidate_id=reservation.candidate_id,
                    event_type="actions_approved",
                    message="人工批准外部动作",
                    details={"preview_version": data.preview_version},
                )
            )
        return await self.execute(reservation_id)

    @traced("external.execute", agent="interview", id_arg="reservation_id")
    async def execute(self, reservation_id):
        async with self.locks.setdefault(reservation_id, asyncio.Lock()):
            meeting_result = None
            for action_type, client in (
                ("meeting", self.meeting),
                ("notification", self.notification),
            ):
                async with self.db.session() as session:
                    reservation = await require(
                        session, Reservation, reservation_id, lock=True
                    )
                    if (
                        reservation.approved_preview_version
                        != reservation.preview_version
                        or not reservation.approved_preview
                    ):
                        raise BusinessError("外部动作未获得当前预览版本授权", 409)
                    row = await session.scalar(
                        select(ActionRecord)
                        .where(
                            ActionRecord.reservation_id == reservation_id,
                            ActionRecord.action_type == action_type,
                        )
                        .with_for_update()
                    )
                    if row is None:
                        row = ActionRecord(
                            reservation_id=reservation_id,
                            action_type=action_type,
                            idempotency_key=f"reservation:{reservation_id}:{action_type}",
                        )
                        session.add(row)
                        await session.flush()
                    if row.status == "succeeded":
                        if action_type == "meeting":
                            meeting_result = row.response_data
                        continue
                    if row.status in ("running", "uncertain"):
                        # A crash after the external side effect is an unknown outcome.
                        row.status = "uncertain"
                        row.last_error = "结果待核实，请先查询平台，不自动重发"
                        await self.audit(
                            session, reservation_id, action_type, "uncertain"
                        )
                        break
                    if not client.configured:
                        row.status = "not_configured"
                        row.last_error = "平台未选定或凭证未配置"
                        await self.audit(
                            session, reservation_id, action_type, "not_configured"
                        )
                        break
                    row.status, row.provider = "running", client.provider
                    row.approved_preview_version = reservation.approved_preview_version
                    row.request_snapshot = reservation.approved_preview
                    row.attempt_count += 1
                    row.started_at = utcnow()
                    preview, key = reservation.approved_preview, row.idempotency_key
                    record_id = row.id
                    await self.audit(session, reservation_id, action_type, "started")
                try:
                    async with asyncio.timeout(self.timeout):
                        result = (
                            await client.create(preview, key)
                            if action_type == "meeting"
                            else await client.send(preview, meeting_result, key)
                        )
                    if not result.get("external_id"):
                        raise ValueError(
                            "Platform did not return an external identifier"
                        )
                except BusinessError as exc:
                    async with self.db.session() as session:
                        row = await require(session, ActionRecord, record_id)
                        row.status, row.last_error = "failed", exc.message
                        await self.audit(session, reservation_id, action_type, "failed")
                    break
                except Exception:  # noqa: BLE001 - external boundary; result may be ambiguous
                    async with self.db.session() as session:
                        row = await require(session, ActionRecord, record_id)
                        row.status, row.last_error = (
                            "uncertain",
                            "外部请求结果不明确，请先核实",
                        )
                        await self.audit(
                            session, reservation_id, action_type, "uncertain"
                        )
                    break
                async with self.db.session() as session:
                    row = await require(session, ActionRecord, record_id)
                    row.status, row.response_data, row.external_id = (
                        "succeeded",
                        result,
                        result["external_id"],
                    )
                    row.meeting_url = result.get("meeting_url")
                    row.completed_at, row.last_error = utcnow(), None
                    await self.audit(session, reservation_id, action_type, "succeeded")
                if action_type == "meeting":
                    meeting_result = result
        return await self.preview(reservation_id)

    async def reconcile(self, reservation_id):
        async with self.locks.setdefault(reservation_id, asyncio.Lock()):
            async with self.db.session() as session:
                await require(session, Reservation, reservation_id)
                rows = (
                    await session.scalars(
                        select(ActionRecord).where(
                            ActionRecord.reservation_id == reservation_id,
                            ActionRecord.status.in_(["uncertain", "running"]),
                        )
                    )
                ).all()
                pending = [
                    (r.id, r.action_type, r.idempotency_key, r.external_id)
                    for r in rows
                ]
            for record_id, action, key, external_id in pending:
                client = self.meeting if action == "meeting" else self.notification
                if not client.configured:
                    continue
                try:
                    async with asyncio.timeout(self.timeout):
                        result = await client.query(key, external_id)
                except Exception:  # noqa: BLE001 - query failure cannot justify another side effect
                    async with self.db.session() as session:
                        row = await require(session, ActionRecord, record_id)
                        row.status, row.last_error = (
                            "uncertain",
                            "平台查询失败，继续保持待核实",
                        )
                        await self.audit(session, reservation_id, action, "uncertain")
                    continue
                if result and result.get("confirmed_absent") is True:
                    async with self.db.session() as session:
                        row = await require(session, ActionRecord, record_id)
                        row.status, row.last_error = (
                            "failed",
                            "平台明确确认该幂等动作未执行，可显式重试",
                        )
                        await self.audit(session, reservation_id, action, "failed")
                elif (
                    result
                    and result.get("external_id")
                    and result.get("status", "succeeded") == "succeeded"
                ):
                    async with self.db.session() as session:
                        row = await require(session, ActionRecord, record_id)
                        row.status, row.response_data, row.external_id = (
                            "succeeded",
                            result,
                            result["external_id"],
                        )
                        row.meeting_url = result.get("meeting_url")
                        row.completed_at, row.last_error = utcnow(), None
                        await self.audit(session, reservation_id, action, "succeeded")
        return await self.preview(reservation_id)
