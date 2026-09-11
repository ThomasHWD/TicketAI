"""Captures de la page FAQ (/tmp/faq), pour relecture visuelle.

Variante de `captures_doc.py` qui **ne passe pas par le formulaire de login** :
la session est ouverte en injectant un JWT signé avec la clé du `.env` dans le
localStorage. Aucun mot de passe n'est requis, et on évite l'annuaire LDAP que
`captures_doc.py` décrit comme intermittent.

Usage :
    PYTHONPATH=. python scripts/captures_faq.py

Jamais `networkidle` : le flux SSE ne se tait jamais (cf. CLAUDE.md).
"""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.core.security import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("TAI_BASE", "http://localhost:5173")
COMPTE = os.environ.get("TAI_USER", "thomas.henwood@onacvg.fr")
OUT = Path("/tmp/faq")
VIEWPORT = {"width": 1280, "height": 900}


def session_localstorage() -> tuple[str, str]:
    """Le couple (token, utilisateur) attendu par `lib/auth.tsx`."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == COMPTE).first()
        if user is None:
            raise SystemExit(f"Compte introuvable : {COMPTE}")
        utilisateur = {
            "id": str(user.id),
            "email": user.email,
            "prenom": user.prenom,
            "nom": user.nom,
            "role": user.role,
            "groupes": [{"id": str(g.id), "nom": g.nom, "domaine": g.domaine, "is_chef": False} for g in user.groupes],
        }
        print(f"compte : {user.email} ({user.role}), {len(utilisateur['groupes'])} groupe(s)")
        return create_access_token(user.id, user.role), json.dumps(utilisateur)
    finally:
        db.close()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    token, utilisateur = session_localstorage()

    def capture(page, nom):
        page.screenshot(path=str(OUT / f"{nom}.png"))
        print(f"  · {nom}.png")

    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page(viewport=VIEWPORT)

        # Une origine est nécessaire avant d'écrire dans le localStorage.
        page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        page.evaluate(
            "([t, u]) => { localStorage.setItem('ticketai.token', t); localStorage.setItem('ticketai.user', u); }",
            [token, utilisateur],
        )

        page.goto(f"{BASE}/faq", wait_until="domcontentloaded")
        page.wait_for_selector("#question-faq", timeout=15_000)
        time.sleep(1.5)
        capture(page, "1-accueil")

        # Reformulation qui retrouve la seule canonique indexée (mesurée à 0,9762).
        page.fill("#question-faq", "quelle est la hauteur d'une pomme ?")
        page.keyboard.press("Enter")
        page.wait_for_selector("article", timeout=30_000)
        time.sleep(1)
        capture(page, "2-resultat")

        page.evaluate("document.documentElement.classList.add('dark')")
        time.sleep(0.6)
        capture(page, "3-resultat-sombre")
        page.evaluate("document.documentElement.classList.remove('dark')")

        # État vide : question sans correspondance.
        page.fill("#question-faq", "quelle est la capitale de la Mongolie ?")
        page.keyboard.press("Enter")
        page.wait_for_selector("text=Aucune réponse ne correspond", timeout=30_000)
        time.sleep(1)
        capture(page, "4-aucun-resultat")

        navigateur.close()

    print(f"\ncaptures dans {OUT}")


if __name__ == "__main__":
    main()
