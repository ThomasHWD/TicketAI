"""Gestion des utilisateurs et des groupes — réservé aux administrateurs."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AdminUser
from app.database import SessionLocal
from app.models.groupe import Groupe, user_groups
from app.models.site_config import SiteConfig
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _entry_value(entry, name: str) -> str | None:
    """Valeur d'un attribut d'une entrée LDAP, ou None si absent/vide."""
    return str(entry[name].value) if name in entry and entry[name].value else None


DB = Annotated[Session, Depends(get_db)]


# ── Schémas ──────────────────────────────────────────────────────────


class GroupeCreate(BaseModel):
    nom: str
    domaine: str


# ── Sérialisation ────────────────────────────────────────────────────


def _serialize_groupe(g: Groupe, include_membres: bool = False, db_session=None) -> dict:
    data = {
        "id": str(g.id),
        "nom": g.nom,
        "domaine": g.domaine,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "nb_membres": len(g.membres),
    }
    if include_membres:
        chef_ids = (
            {
                row.user_id
                for row in db_session.execute(
                    user_groups.select().where(
                        user_groups.c.groupe_id == g.id,
                        user_groups.c.is_chef.is_(True),
                    )
                )
            }
            if db_session
            else set()
        )
        data["membres"] = [{**_serialize_user_summary(u), "is_chef": u.id in chef_ids} for u in g.membres]
    return data


def _serialize_user_summary(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "prenom": u.prenom,
        "nom": u.nom,
        "role": u.role,
        "departement": u.departement,
        "is_gestionnaire": u.is_gestionnaire,
        "groupes": [{"id": str(g.id), "nom": g.nom, "domaine": g.domaine} for g in u.groupes],
    }


# ── Gestionnaires / utilisateurs ─────────────────────────────────────


@router.get("/gestionnaires")
def list_gestionnaires(_: AdminUser, db: DB):
    """Liste les membres du groupe gestionnaire depuis l'AD (avec fallback base)."""
    from ldap3 import Connection

    from app.config import settings
    from app.services.ldap_auth import _make_server

    if settings.auth_mode == "ldap":
        try:
            server = _make_server(settings.ldap_server_url)
            svc = Connection(
                server,
                user=settings.ldap_bind_dn,
                password=settings.ldap_bind_password,
                auto_bind=True,
                receive_timeout=settings.ldap_timeout,
            )
            # Récupère le DN exact du groupe
            svc.search(settings.ldap_user_search_base, f"(cn={settings.ldap_group_gestionnaire})", attributes=["cn"])
            if not svc.entries:
                svc.unbind()
                return []
            group_dn = svc.entries[0].entry_dn

            # Recherche récursive (LDAP_MATCHING_RULE_IN_CHAIN) pour inclure les sous-groupes
            svc.search(
                settings.ldap_user_search_base,
                f"(memberOf:1.2.840.113556.1.4.1941:={group_dn})",
                attributes=[
                    settings.ldap_attr_email,
                    settings.ldap_attr_firstname,
                    settings.ldap_attr_lastname,
                    settings.ldap_attr_department,
                ],
            )

            result = []
            emails_vus: set[str] = set()
            for e in svc.entries:
                email = _entry_value(e, settings.ldap_attr_email)
                if not email or email in emails_vus:
                    continue
                emails_vus.add(email)
                db_user = db.query(User).filter(User.email == email).first()
                result.append(
                    {
                        "id": str(db_user.id) if db_user else None,
                        "email": email,
                        "prenom": _entry_value(e, settings.ldap_attr_firstname),
                        "nom": _entry_value(e, settings.ldap_attr_lastname),
                        "departement": _entry_value(e, settings.ldap_attr_department),
                        "is_gestionnaire": True,
                        "role": db_user.role if db_user else "USER",
                    }
                )
            svc.unbind()
            return sorted(result, key=lambda u: (u["nom"] or "", u["prenom"] or ""))
        except Exception:
            pass  # fallback base si l'AD est injoignable

    # Fallback : base de données
    users = db.query(User).filter(User.is_gestionnaire.is_(True)).order_by(User.nom, User.prenom).all()
    return [_serialize_user_summary(u) for u in users]


# ── Groupes ──────────────────────────────────────────────────────────


@router.get("/groupes")
def list_groupes(_: AdminUser, db: DB):
    """Liste tous les groupes avec leur nombre de membres."""
    groupes = db.query(Groupe).order_by(Groupe.domaine, Groupe.nom).all()
    return [_serialize_groupe(g, include_membres=True, db_session=db) for g in groupes]


@router.get("/domaines")
def list_domaines(_: AdminUser, db: DB):
    """Liste les domaines existants (valeurs distinctes sur les groupes)."""
    rows = db.query(Groupe.domaine).distinct().order_by(Groupe.domaine).all()
    return [r[0] for r in rows]


@router.post("/groupes", status_code=status.HTTP_201_CREATED)
def create_groupe(body: GroupeCreate, _: AdminUser, db: DB):
    """Crée un groupe."""
    domaine = body.domaine.strip().upper()
    if not domaine:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Le domaine est obligatoire.")
    groupe = Groupe(nom=body.nom, domaine=domaine)
    db.add(groupe)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un groupe existe déjà pour le domaine {domaine}.",
        ) from err
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_groupe(groupe_id: UUID, _: AdminUser, db: DB):
    """Supprime un groupe et ses associations membres."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    db.delete(groupe)
    db.commit()


# ── Membres ──────────────────────────────────────────────────────────


@router.post("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_201_CREATED)
def add_membre(groupe_id: UUID, user_id: str, _: AdminUser, db: DB):
    """Ajoute un utilisateur dans un groupe. user_id peut être un UUID ou un email (provisionnement JIT)."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")

    # Résolution de l'utilisateur : UUID en base ou email (provisionnement depuis l'AD)
    user = None
    if "@" in user_id:
        user = db.query(User).filter(User.email == user_id).first()
        if user is None:
            # Provisionnement JIT depuis l'AD
            from ldap3 import Connection

            from app.config import settings
            from app.services.ldap_auth import _make_server, _search_attributes

            try:
                server = _make_server(settings.ldap_server_url)
                svc = Connection(
                    server,
                    user=settings.ldap_bind_dn,
                    password=settings.ldap_bind_password,
                    auto_bind=True,
                    receive_timeout=settings.ldap_timeout,
                )
                svc.search(
                    settings.ldap_user_search_base,
                    f"({settings.ldap_attr_email}={user_id})",
                    attributes=_search_attributes(),
                )
                if svc.entries:
                    e = svc.entries[0]
                    user = User(
                        email=user_id,
                        prenom=_entry_value(e, settings.ldap_attr_firstname),
                        nom=_entry_value(e, settings.ldap_attr_lastname),
                        departement=_entry_value(e, settings.ldap_attr_department),
                        is_gestionnaire=True,
                        role="USER",
                    )
                    db.add(user)
                    db.flush()
                svc.unbind()
            except Exception:
                pass
    else:
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
        except ValueError:
            pass

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    if user not in groupe.membres:
        groupe.membres.append(user)
        db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_membre(groupe_id: UUID, user_id: UUID, _: AdminUser, db: DB):
    """Retire un utilisateur d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user and user in groupe.membres:
        groupe.membres.remove(user)
        db.commit()


# ── Configuration du site ────────────────────────────────────────────

# Valeurs par défaut pour chaque clé de config
_CONFIG_DEFAULTS: dict[str, Any] = {
    "banner": {"active": False, "message": "", "url": ""},
}


class ConfigPayload(BaseModel):
    value: Any


@router.get("/config")
def get_config(db: DB):
    """Retourne toute la configuration du site (accessible à tout utilisateur authentifié)."""
    rows = db.query(SiteConfig).all()
    result = dict(_CONFIG_DEFAULTS)
    for row in rows:
        result[row.key] = row.value
    return result


@router.put("/config/{key}")
def set_config(key: str, body: ConfigPayload, _: AdminUser, db: DB):
    """Met à jour une clé de configuration (admin uniquement)."""
    if key not in _CONFIG_DEFAULTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Clé de configuration inconnue : {key}")
    row = db.query(SiteConfig).filter(SiteConfig.key == key).first()
    if row is None:
        row = SiteConfig(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    db.refresh(row)
    return {"key": row.key, "value": row.value}


class ChefPayload(BaseModel):
    is_chef: bool


@router.put("/groupes/{groupe_id}/membres/{user_id}/chef")
def set_chef(groupe_id: UUID, user_id: UUID, body: ChefPayload, _: AdminUser, db: DB):
    """Désigne ou retire le rôle de chef pour un membre d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user not in groupe.membres:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable dans ce groupe.")
    db.execute(
        user_groups.update()
        .where(user_groups.c.groupe_id == groupe_id, user_groups.c.user_id == user_id)
        .values(is_chef=body.is_chef)
    )
    db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)
