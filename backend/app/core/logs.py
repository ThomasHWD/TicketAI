"""Single logging setup for the API and the Celery workers.

Without it, uvicorn configures only its own loggers: every `logger.info` under `app.*` was dropped in the API, and
warnings came out bare (no time, level or module). Worker lines carried no task id, so 4 concurrent question jobs
interleaved with no way to tell which guard verdict belonged to which question.
"""

import logging
import logging.config
from contextvars import ContextVar

from celery.app.trace import LOG_SUCCESS

# One context per thread: the Celery pool is `threads`, each task sees only its own prefix.
_contexte: ContextVar[str] = ContextVar("contexte_log", default="")


def lier(**champs: object) -> None:
    """Add `key=value` fields to the prefix of every following line of the current task."""
    ajout = " ".join(f"{cle}={valeur}" for cle, valeur in champs.items())
    _contexte.set(f"{_contexte.get()} {ajout}".strip())


def delier() -> None:
    _contexte.set("")


class _Contexte(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        contexte = _contexte.get()
        record.contexte = f"[{contexte}] " if contexte else ""
        return True


class _SansValeurDeRetour(logging.Filter):
    """Celery writes each task's return value into its « succeeded » line: for question_job, the question and the
    generated answer in clear — HR questions, never reviewed. The runtime stays; the value is in the result backend."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg == LOG_SUCCESS:
            record.msg = "Task %(name)s[%(id)s] succeeded in %(runtime)ss"
        return True


_SANS_VALEUR_DE_RETOUR = _SansValeurDeRetour()  # one instance: addFilter dedupes by identity


def configurer_logs(niveau: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"contexte": {"()": _Contexte}},
            "formatters": {
                "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(contexte)s%(message)s"},
            },
            "handlers": {
                "stderr": {"class": "logging.StreamHandler", "formatter": "standard", "filters": ["contexte"]},
            },
            "root": {"level": niveau.upper(), "handlers": ["stderr"]},
            "loggers": {
                # Startup and errors in the common format. uvicorn.access is left alone: --no-access-log empties
                # its handlers, re-adding one here would bring the access log back.
                "uvicorn": {"handlers": ["stderr"], "propagate": False},
                # One INFO line per outgoing HTTP call (Albert, Qdrant): volume, no information.
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
            },
        }
    )
    logging.getLogger("celery.app.trace").addFilter(_SANS_VALEUR_DE_RETOUR)
