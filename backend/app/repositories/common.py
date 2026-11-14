from datetime import datetime
from decimal import Decimal

from sqlalchemy import inspect, select

from app.core.errors import BusinessError


async def require(session, model, record_id, *, lock=False):
    query = select(model).where(model.id == record_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise BusinessError("记录不存在", 404)
    return row


def serialize(row):
    data = {}
    for column in inspect(type(row)).columns:
        value = getattr(row, column.key)
        if isinstance(value, datetime):
            value = value.isoformat() + "Z"
        elif isinstance(value, Decimal):
            value = float(value)
        elif (
            isinstance(value, int)
            and not isinstance(value, bool)
            and (column.key == "id" or column.key.endswith("_id"))
        ):
            value = str(value)
        data[column.key] = value
    return data
