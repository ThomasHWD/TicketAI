"""SSE stream: an open tab must not spin the event loop, and closing it must release the user's locks."""

import asyncio
import uuid

import anyio
from app.api.v1 import sse


class _PubSubRedis:
    """Mimics redis.asyncio: get_message() returns at once unless given a timeout (default 0.0)."""

    def __init__(self):
        self.appels = 0

    async def subscribe(self, *canaux):
        pass

    async def psubscribe(self, *motifs):
        pass

    async def unsubscribe(self):
        await asyncio.sleep(0)  # real network I/O: a point where a pending cancellation strikes

    async def punsubscribe(self):
        await asyncio.sleep(0)

    async def aclose(self):
        await asyncio.sleep(0)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        self.appels += 1
        await asyncio.sleep(timeout or 0)
        return None


class _Redis:
    def __init__(self):
        self.ps = _PubSubRedis()

    def pubsub(self):
        return self.ps

    async def aclose(self):
        pass


class _Requete:
    async def is_disconnected(self):
        return False


class _User:
    id = uuid.uuid4()
    role = "USER"
    groupes = []


async def _ouvrir_puis_couper(monkeypatch, duree: float):
    redis = _Redis()
    liberes = []
    monkeypatch.setattr(sse.aioredis, "from_url", lambda *_a, **_k: redis)
    monkeypatch.setattr(sse, "_release_user_lock", liberes.append)

    async def lire():
        async for _ in sse._stream(_Requete(), _User()):
            pass

    # Starlette cancels through an anyio cancel scope: unlike a bare task.cancel(), every await left in the
    # generator's finally raises again — which is what skipped the release.
    async with anyio.create_task_group() as groupe:
        groupe.start_soon(lire)
        await anyio.sleep(duree)
        groupe.cancel_scope.cancel()
    await asyncio.sleep(0.05)
    return redis.ps.appels, liberes


def test_un_flux_ouvert_attend_ses_messages_au_lieu_de_tourner(monkeypatch):
    appels, _ = anyio.run(_ouvrir_puis_couper, monkeypatch, 1.0)
    assert appels <= 5, f"{appels} lectures en 1 s : la boucle tourne à vide"


def test_la_deconnexion_libere_les_verrous_de_l_utilisateur(monkeypatch):
    _, liberes = anyio.run(_ouvrir_puis_couper, monkeypatch, 0.2)
    assert liberes == [_User.id]
