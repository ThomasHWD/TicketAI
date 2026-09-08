#!/usr/bin/env python3
"""
Test de charge TicketAI — endpoints en lecture seule.

Usage (depuis backend/) :
    PYTHONPATH=. python scripts/load_test.py [options]

Options :
    --users N       Utilisateurs virtuels concurrents (défaut : 10)
    --duration S    Durée en secondes (défaut : 30)
    --ramp S        Montée en charge progressive sur S secondes (défaut : 5)
    --url URL       Base URL (défaut : http://localhost:8000)
    --write         Inclure les soumissions de tickets (ATTENTION : charge Celery)

Prérequis : un utilisateur existe en base. Le script forge le JWT directement
depuis jwt_secret_key — aucun appel LDAP, aucun appel Albert.
"""

import argparse
import asyncio
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from jose import jwt
from sqlalchemy.orm import joinedload

# ── Helpers ───────────────────────────────────────────────────────────────────


def _forge_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _pick_users(n: int) -> list[dict]:
    """Retourne jusqu'à n utilisateurs depuis la base (tous rôles confondus)."""
    db = SessionLocal()
    try:
        users = db.query(User).options(joinedload(User.groupes)).limit(max(n, 5)).all()
        if not users:
            raise SystemExit(
                "Aucun utilisateur en base. Lance d'abord :\n  PYTHONPATH=. python scripts/seed_validators.py"
            )
        result = []
        for u in users:
            result.append(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "role": u.role,
                    "has_groups": bool(u.groupes),
                    "token": _forge_token(str(u.id), u.role),
                }
            )
        return result
    finally:
        db.close()


# ── Scénarios ─────────────────────────────────────────────────────────────────


def _build_scenarios(base_url: str, include_write: bool) -> list[dict]:
    """Retourne la liste de requêtes (méthode, path, poids) à tourner en round-robin."""
    reads = [
        ("GET", "/health", 2),
        ("GET", "/api/v1/auth/me", 3),
        ("GET", "/api/v1/tickets?page=1&limit=10", 5),
        ("GET", "/api/v1/tickets?page=1&limit=10&statut=RÉPONDU", 3),
        ("GET", "/api/v1/tickets?page=2&limit=10", 2),
        ("GET", "/api/v1/tickets/domaines", 2),
        ("GET", "/api/v1/notifications", 2),
        ("GET", "/api/v1/stats/dashboard?periode=semaine", 2),
        ("GET", "/api/v1/stats/dashboard?periode=mois", 1),
        ("GET", "/api/v1/documents?page=1&limit=20", 2),
        # admin/health : diagnostic sysadmin uniquement, exclu de la rotation de charge
    ]
    writes = [
        ("POST_TICKET", "/api/v1/tickets", 1),
    ]
    scenarios = []
    for method, path, weight in reads:
        scenarios.extend([{"method": method, "url": base_url + path}] * weight)
    if include_write:
        for method, path, weight in writes:
            scenarios.extend([{"method": method, "url": base_url + path}] * weight)
    return scenarios


# ── Worker ────────────────────────────────────────────────────────────────────


async def _virtual_user(
    user: dict,
    scenarios: list[dict],
    results: dict,
    stop_event: asyncio.Event,
    semaphore: asyncio.Semaphore,
    ramp_delay: float,
):
    await asyncio.sleep(ramp_delay)
    headers = {"Authorization": f"Bearer {user['token']}"}
    idx = 0

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        while not stop_event.is_set():
            scenario = scenarios[idx % len(scenarios)]
            idx += 1

            method = scenario["method"]
            url = scenario["url"]
            label = f"{method} {url.split('//')[1].split('/', 1)[1] if '//' in url else url}"

            # Normalise le label (enlève les query strings pour l'agrégation)
            path = url.split("?")[0].replace(url.split("/api")[0], "")
            label = f"{method} {path}"

            async with semaphore:
                t0 = time.perf_counter()
                status_code = 0
                error = None
                try:
                    if method == "GET":
                        resp = await client.get(url, headers=headers)
                    elif method == "POST_TICKET":
                        resp = await client.post(
                            url,
                            json={
                                "question": "Quel est le délai de préavis pour une démission ?",
                                "domaine": "RH",
                                "objet": "Test de charge",
                            },
                            headers=headers,
                        )
                    status_code = resp.status_code
                except Exception as e:
                    error = str(e)
                finally:
                    elapsed_ms = (time.perf_counter() - t0) * 1000

                results[label]["latencies"].append(elapsed_ms)
                if error:
                    results[label]["errors"] += 1
                elif status_code >= 500:
                    results[label]["errors"] += 1
                elif status_code in (401, 403, 404):
                    results[label]["skipped"] += 1
                else:
                    results[label]["ok"] += 1


# ── Rapport ───────────────────────────────────────────────────────────────────


def _pct(lst: list[float], p: float) -> float:
    if not lst:
        return 0.0
    return statistics.quantiles(sorted(lst), n=100)[int(p) - 1]


def _print_report(results: dict, duration: float, n_users: int) -> None:
    total_req = sum(sum(v["latencies"] and [1] or []) for v in results.values())
    total_req = sum(len(v["latencies"]) for v in results.values())
    total_ok = sum(v["ok"] for v in results.values())
    total_err = sum(v["errors"] for v in results.values())

    print()
    print("=" * 80)
    print(f"  TEST DE CHARGE — {n_users} utilisateurs, {duration:.0f}s")
    print("=" * 80)
    print(f"  Total requêtes : {total_req:>6}  |  OK : {total_ok}  |  Erreurs : {total_err}")
    print(f"  Débit global   : {total_req / duration:>6.1f} req/s")
    print()
    print(f"  {'Endpoint':<45} {'n':>5} {'err':>4} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}")
    print(f"  {'-' * 45} {'---':>5} {'---':>4} {'ms':>7} {'ms':>7} {'ms':>7} {'ms':>7}")

    for label, data in sorted(results.items()):
        lats = data["latencies"]
        if not lats:
            continue
        n = len(lats)
        err = data["errors"]
        p50 = _pct(lats, 50)
        p95 = _pct(lats, 95)
        p99 = _pct(lats, 99)
        mx = max(lats)
        flag = " !" if err > 0 or p95 > 500 else ""
        short = label[-44:] if len(label) > 44 else label
        print(f"  {short:<45} {n:>5} {err:>4} {p50:>7.0f} {p95:>7.0f} {p99:>7.0f} {mx:>7.0f}{flag}")

    print("=" * 80)

    # Alertes
    alerts = []
    for label, data in results.items():
        lats = data["latencies"]
        if not lats:
            continue
        if data["errors"] / len(lats) > 0.05:
            alerts.append(f"  ERREURS élevées sur {label} : {data['errors']}/{len(lats)}")
        if _pct(lats, 95) > 1000:
            alerts.append(f"  LENTEUR p95>{_pct(lats, 95):.0f}ms sur {label}")
    if alerts:
        print()
        print("  Alertes :")
        for a in alerts:
            print(a)
        print()


# ── Main ──────────────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> None:
    print("Récupération des utilisateurs…")
    users = _pick_users(args.users)
    emails = ", ".join(u["email"] for u in users[:3])
    suffix = "…" if len(users) > 3 else ""
    print(f"  {len(users)} utilisateur(s) trouvé(s) : {emails}{suffix}")

    scenarios = _build_scenarios(args.url, args.write)
    print(f"  {len(scenarios)} scénarios pondérés  |  write={'oui' if args.write else 'non'}")
    print(f"  {args.users} VU  |  durée {args.duration}s  |  ramp {args.ramp}s")

    results: dict = defaultdict(lambda: {"latencies": [], "ok": 0, "errors": 0, "skipped": 0})
    stop_event = asyncio.Event()
    semaphore = asyncio.Semaphore(args.users * 2)  # max connexions simultanées

    # Distribue les users en round-robin si on en a moins que VU
    assigned_users = [users[i % len(users)] for i in range(args.users)]
    ramp_delays = [i * (args.ramp / args.users) for i in range(args.users)]

    tasks = [
        asyncio.create_task(_virtual_user(u, scenarios, results, stop_event, semaphore, delay))
        for u, delay in zip(assigned_users, ramp_delays, strict=False)
    ]

    print("\nDémarrage… (Ctrl+C pour arrêter)")
    t_start = time.perf_counter()

    try:
        await asyncio.sleep(args.duration)
    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.perf_counter() - t_start
    _print_report(dict(results), elapsed, args.users)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=10, help="Utilisateurs virtuels concurrents")
    parser.add_argument("--duration", type=float, default=30, help="Durée en secondes")
    parser.add_argument("--ramp", type=float, default=5, help="Montée en charge (secondes)")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="Base URL de l'API")
    parser.add_argument("--write", action="store_true", help="Inclure les soumissions de tickets")
    args = parser.parse_args()

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
