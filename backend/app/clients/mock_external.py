"""Explicit demo adapters: deterministic IDs, no network or actual delivery."""

from hashlib import sha256


class MockMeetingClient:
    configured = True
    provider = "mock"

    async def create(self, approved_preview, idempotency_key):
        return {
            "external_id": "mock-meeting-"
            + sha256(idempotency_key.encode()).hexdigest(),
            "status": "succeeded",
            "simulated": True,
        }

    async def query(self, idempotency_key, external_id):
        # No durable provider ledger: absence cannot be asserted after restart.
        return None


class MockNotificationClient:
    configured = True
    provider = "mock"

    async def send(self, approved_preview, meeting_result, idempotency_key):
        return {
            "external_id": "mock-notification-"
            + sha256(idempotency_key.encode()).hexdigest(),
            "status": "succeeded",
            "simulated": True,
        }

    async def query(self, idempotency_key, external_id):
        return None
