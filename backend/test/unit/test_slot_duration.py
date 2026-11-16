from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import BusinessError
from app.schemas.business import SlotInput
from app.services.schedule_service.scheduling import slot_values


@pytest.mark.parametrize("minutes", [15, 30, 45, 60, 90])
def test_manual_slot_duration_is_preserved(minutes):
    start = datetime(2026, 11, 15, 23, 45, tzinfo=UTC)
    values = slot_values(
        SlotInput(
            starts_at=start,
            ends_at=start + timedelta(minutes=minutes),
            timezone="Asia/Shanghai",
        )
    )
    assert values["ends_at"] - values["starts_at"] == timedelta(minutes=minutes)


@pytest.mark.parametrize("minutes", [0, -15])
def test_end_must_be_after_start(minutes):
    start = datetime(2026, 11, 15, tzinfo=UTC)
    with pytest.raises(BusinessError, match="结束时间须晚于开始时间"):
        slot_values(
            SlotInput(
                starts_at=start,
                ends_at=start + timedelta(minutes=minutes),
                timezone="Asia/Shanghai",
            )
        )
