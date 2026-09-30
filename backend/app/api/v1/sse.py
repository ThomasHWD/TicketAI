"""Per-user SSE stream. Subscriptions by role: USER → user:{id}+global; VALIDATEUR → +domain:{dom} per group; ADMIN"""

import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])

_PING_INTERVAL = 20.0  # secondes entre deux keepalive comments
# get_message() defaults to timeout=0.0 — it returns at once, and the loop spun at ~50k turns/s per open tab, pinning
# the event loop at 100 % CPU: broadcasts timed out and sync routes stalled > 150 s (measured 29/09/2026).
_ATTENTE_MESSAGE = 0.5

# Cleanup tasks detached from the cancelled stream — kept referenced so they are not garbage-collected mid-flight.
_fermetures: set[asyncio.Task] = set()


def _release_user_lock(user_id) -> None:
    """Libère tout verrou détenu par cet utilisateur — appelé à la déconnexion SSE."""
    db = SessionLocal()
    try:
        db.query(Ticket).filter(Ticket.locked_by == user_id).update(
            {
                Ticket.locked_by: None,
                Ticket.locked_at: None,
                Ticket.lock_expires_at: None,
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception as e:
        logger.error("Lock release failed for user %s: %s", user_id, e)
    finally:
        db.close()


async def _stream(request: Request, user):
    channels = [f"sse:user:{user.id}", "sse:global"]
    use_domain_pattern = False

    if user.role == "ADMIN":
        channels.append("sse:admin")
    domaines = [groupe.domaine for groupe in user.groupes]
    if domaines:
        for domaine in domaines:
            channels.append(f"sse:domain:{domaine}")
    elif user.role == "ADMIN":
        use_domain_pattern = True

    r = aioredis.from_url(settings.valkey_url)
    pubsub = r.pubsub()

    try:
        await pubsub.subscribe(*channels)
        if use_domain_pattern:
            await pubsub.psubscribe("sse:domain:*")
        yield "retry: 5000\n\n"

        last_ping = asyncio.get_event_loop().time()

        while True:
            if await request.is_disconnected():
                break

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_ATTENTE_MESSAGE)

            now = asyncio.get_event_loop().time()

            if message is not None:
                # Les pmessage (pattern) et message ont tous deux leur payload dans "data"
                msg_type = message.get("type", "")
                if msg_type in ("message", "pmessage"):
                    last_ping = now
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
            elif now - last_ping >= _PING_INTERVAL:
                last_ping = now
                yield ":ping\n\n"

    finally:
        # First, and with no await before it: on disconnect the stream is cancelled, and any await in this block
        # re-raises CancelledError (a BaseException) — the release used to sit after the unsubscribe and never ran.
        _release_user_lock(user.id)
        tache = asyncio.get_running_loop().create_task(_fermer(pubsub, r, use_domain_pattern))
        _fermetures.add(tache)
        tache.add_done_callback(_fermetures.discard)


async def _fermer(pubsub, r, use_domain_pattern: bool) -> None:
    try:
        await pubsub.unsubscribe()
        if use_domain_pattern:
            await pubsub.punsubscribe()
        await pubsub.aclose()
        await r.aclose()
    except Exception as e:
        logger.warning("Fermeture du flux SSE incomplète : %s", e)


@router.get("/sse/stream")
async def sse_stream(request: Request, current_user: CurrentUser):
    return StreamingResponse(
        _stream(request, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
