from app.core.errors import BusinessError


class NotificationClient:
    """Platform adapter boundary; never simulate notification delivery."""

    configured = False
    provider = None

    async def send(self, approved_preview, meeting_result, idempotency_key):
        raise BusinessError("通知平台尚未配置或选定", 503)

    async def query(self, idempotency_key, external_id):
        return None
