from app.core.errors import BusinessError


class MeetingClient:
    """Platform adapter boundary. Implement once the meeting provider is selected."""

    configured = False
    provider = None

    async def create(self, approved_preview, idempotency_key):
        raise BusinessError("会议平台尚未配置或选定", 503)

    async def query(self, idempotency_key, external_id):
        return None
