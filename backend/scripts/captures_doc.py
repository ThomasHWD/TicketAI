"""Capture les écrans de l'application pour la documentation (Docs/images/).

Usage :
    TAI_USER=... TAI_PASS=... .venv/bin/python scripts/captures_doc.py

Les identifiants ne sont jamais écrits sur disque : ils sont lus dans
l'environnement et utilisés uniquement pour le login initial.
"""

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("TAI_BASE", "http://localhost:5173")
USER = os.environ.get("TAI_USER")
PASS = os.environ.get("TAI_PASS")
OUT = Path(__file__).resolve().parents[2] / "Docs" / "images"
VIEWPORT = {"width": 1600, "height": 1000}


def log(msg):
    print(msg, flush=True)


def login(page, tentatives=4):
    """Connexion, avec réessais.

    L'annuaire est intermittent : `authenticate()` intercepte `LDAPException` et
    renvoie `None`, si bien qu'un timeout LDAP produit exactement le même
    « Identifiant ou mot de passe incorrect » qu'un mauvais mot de passe. Les
    mêmes identifiants échouent puis réussissent d'une minute à l'autre — d'où
    ces réessais espacés (le login est limité à 10 tentatives/min/IP).
    """
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    time.sleep(2)
    page.screenshot(path=str(OUT / "00-login.png"))
    log("  · capture: 00-login.png")

    for n in range(1, tentatives + 1):
        page.fill("input[type='text'], input[name='username']", USER)
        page.fill("input[type='password']", PASS)
        page.click("button[type='submit']")
        try:
            page.wait_for_url(lambda u: "/login" not in u, timeout=120_000)
            time.sleep(4)
            if n > 1:
                log(f"  (connecté à la tentative {n})")
            return True
        except Exception:
            if n == tentatives:
                page.screenshot(path=str(OUT / "99-login-echec.png"))
                log(f"  ! login échoué après {tentatives} tentatives — voir 99-login-echec.png")
                return False
            log(f"  ~ tentative {n} refusée (annuaire instable), nouvel essai dans 20 s…")
            time.sleep(20)
            page.goto(f"{BASE}/login", wait_until="domcontentloaded")
            time.sleep(2)
    return False


def shoot(page, name, url, *, wait=3.5, full=False, before=None):
    """Navigue et capture. Renvoie l'URL finale (pour détecter les redirections).

    NB : on n'utilise **jamais** `networkidle`. L'application garde une connexion
    SSE ouverte en permanence (`/api/v1/sse/stream`), donc le réseau n'est jamais
    au repos et l'attente expirerait systématiquement.
    """
    try:
        page.goto(f"{BASE}{url}", wait_until="domcontentloaded", timeout=45_000)
    except Exception as e:
        log(f"  ! {name}: navigation échouée ({type(e).__name__})")
        return None
    # Laisse React Query charger et peindre les données.
    time.sleep(wait)
    if before:
        try:
            before(page)
            time.sleep(1.2)
        except Exception as e:
            log(f"  ~ {name}: action optionnelle ignorée ({type(e).__name__})")
    final = page.url.replace(BASE, "")
    # Une redirection = accès refusé (barrière de rôle) : la capture ne montrerait
    # pas l'écran demandé, on ne la conserve pas.
    if final.split("?")[0].rstrip("/") != url.split("?")[0].rstrip("/"):
        log(f"  ~ {name}: accès refusé, redirigé vers {final} — non capturé")
        return final
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    log(f"  · capture: {name}.png")
    return final


def ouvrir_premier_ticket(page):
    """Ouvre le premier ticket de la liste et renvoie son URL.

    Les lignes du tableau ne sont pas des `<a>` : la navigation se fait au clic
    sur la ligne. On clique donc, puis on lit l'URL obtenue.
    """
    try:
        page.goto(f"{BASE}/tickets", wait_until="domcontentloaded", timeout=45_000)
        time.sleep(4)
        # On évite les tickets « En cours » (l'IA travaille encore : la ligne
        # n'ouvre pas de détail exploitable) et on privilégie une réponse en
        # attente, seul cas où le panneau Valider / Corriger / Rejeter s'affiche.
        lignes = page.locator("tbody tr")
        for i in range(lignes.count()):
            ligne = lignes.nth(i)
            if "En cours" in ligne.inner_text():
                continue
            ligne.click()
            try:
                page.wait_for_url(lambda u: "/tickets/" in u, timeout=15_000)
            except Exception:
                page.goto(f"{BASE}/tickets", wait_until="domcontentloaded")
                time.sleep(3)
                lignes = page.locator("tbody tr")
                continue
            time.sleep(4)
            return page.url.replace(BASE, "")
        return None
    except Exception as e:
        log(f"  ~ ouverture du ticket impossible ({type(e).__name__})")
        return None


def main():
    if not USER or not PASS:
        sys.exit("TAI_USER et TAI_PASS doivent être définis dans l'environnement.")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, locale="fr-FR")
        page = ctx.new_page()

        log("Connexion…")
        if not login(page):
            browser.close()
            sys.exit(1)
        log(f"Connecté — page d'arrivée : {page.url.replace(BASE, '')}")

        log("Espace utilisateur…")
        shoot(page, "10-mon-espace", "/mon-espace", full=True)
        shoot(page, "11-nouveau-ticket", "/nouveau-ticket")
        shoot(page, "12-suggestion", "/suggestion")
        shoot(page, "13-historique", "/historique", full=True)

        log("Backoffice…")
        shoot(page, "20-tickets-liste", "/tickets", full=True)
        shoot(page, "21-dashboard", "/", full=True)
        shoot(page, "22-mon-suivi", "/mon-suivi", full=True)
        shoot(page, "23-reponses-canoniques", "/reponses-enregistrees", full=True)
        shoot(page, "24-reponses-a-relire", "/reponses-enregistrees?onglet=a_relire", full=True)
        shoot(page, "25-reponses-obsoletes", "/reponses-enregistrees?onglet=obsoletes", full=True)
        shoot(page, "26-base-connaissances", "/base-de-connaissances", full=True)
        shoot(page, "27-angles-morts", "/base-de-connaissances?onglet=angles-morts", full=True)

        log("Détail d'un ticket…")
        url_ticket = ouvrir_premier_ticket(page)
        if url_ticket:
            page.screenshot(path=str(OUT / "30-ticket-detail.png"), full_page=True)
            log("  · capture: 30-ticket-detail.png")
            # La timeline est dans une fenêtre modale déclenchée par un bouton.
            for libelle in ("Workflow", "Historique", "Suivi"):
                try:
                    page.get_by_role("button", name=libelle).first.click(timeout=4000)
                    time.sleep(2)
                    page.screenshot(path=str(OUT / "31-ticket-workflow.png"))
                    log(f"  · capture: 31-ticket-workflow.png (bouton « {libelle} »)")
                    break
                except Exception:
                    continue
            else:
                log("  ~ bouton de workflow non trouvé — timeline non capturée")
        else:
            log("  ~ aucun ticket ouvrable : détail et workflow non capturés")

        # Les écrans d'administration exigent le rôle ADMIN ; avec un compte
        # validateur, /admin* redirige vers / (vérifié).
        log("Administration : ignorée (nécessite un compte ADMIN)")

        browser.close()
    log(f"\nTerminé. Images dans {OUT}")


if __name__ == "__main__":
    main()
