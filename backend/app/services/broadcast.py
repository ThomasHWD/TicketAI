import json
import logging

import redis
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


def broadcast_sync(channel: str, event_type: str, payload: dict) -> None:
    """Publie un événement SSE sur un canal Redis (sync — pour les workers Celery)."""
    try:
        r = redis.from_url(settings.valkey_url, socket_connect_timeout=2)
        r.publish(channel, json.dumps({"type": event_type, "payload": payload}))
        r.close()
    except Exception as e:
        logger.error("broadcast_sync failed on %s: %s", channel, e)


async def broadcast_async(channel: str, event_type: str, payload: dict) -> None:
    """Publie un événement SSE sur un canal Redis (async — pour les endpoints FastAPI)."""
    try:
        r = aioredis.from_url(settings.valkey_url, socket_connect_timeout=2)
        await r.publish(channel, json.dumps({"type": event_type, "payload": payload}))
        await r.aclose()
    except Exception as e:
        logger.error("broadcast_async failed on %s: %s", channel, e)
