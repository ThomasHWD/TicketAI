from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import AdminUser
from app.database import SessionLocal
from app.models.groupe import Groupe, user_groups
from app.models.user import User
from app.schemas.admin import ChefPayload
from app.services.admin_service import entry_value, serialize_groupe, serialize_user_summary
from app.services.broadcast import broadcast_sync

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


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
            svc.search(settings.ldap_user_search_base, f"(cn={settings.ldap_group_gestionnaire})", attributes=["cn"])
            if not svc.entries:
                svc.unbind()
                return []
            group_dn = svc.entries[0].entry_dn

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
                email = entry_value(e, settings.ldap_attr_email)
                if not email or email in emails_vus:
                    continue
                emails_vus.add(email)
                db_user = db.query(User).filter(User.email == email).first()
                result.append(
                    {
                        "id": str(db_user.id) if db_user else None,
                        "email": email,
                        "prenom": entry_value(e, settings.ldap_attr_firstname),
                        "nom": entry_value(e, settings.ldap_attr_lastname),
                        "departement": entry_value(e, settings.ldap_attr_department),
                        "is_gestionnaire": True,
                        "role": db_user.role if db_user else "USER",
                    }
                )
            svc.unbind()
            db_gestionnaires = db.query(User).filter(User.is_gestionnaire.is_(True)).all()
            for u in db_gestionnaires:
                if u.email and u.email not in emails_vus:
                    result.append(serialize_user_summary(u))
            return sorted(result, key=lambda u: (u["nom"] or "", u["prenom"] or ""))
        except Exception:
            pass

    users = db.query(User).filter(User.is_gestionnaire.is_(True)).order_by(User.nom, User.prenom).all()
    return [serialize_user_summary(u) for u in users]


@router.post("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_201_CREATED)
def add_membre(groupe_id: UUID, user_id: str, _: AdminUser, db: DB):
    """Ajoute un utilisateur dans un groupe. user_id peut être un UUID ou un email."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")

    user = None
    if "@" in user_id:
        user = db.query(User).filter(User.email == user_id).first()
        if user is None:
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
                        prenom=entry_value(e, settings.ldap_attr_firstname),
                        nom=entry_value(e, settings.ldap_attr_lastname),
                        departement=entry_value(e, settings.ldap_attr_department),
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
    broadcast_sync("sse:admin", "group_updated", {})
    return serialize_groupe(groupe, include_membres=True, db_session=db)


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
    broadcast_sync("sse:admin", "group_updated", {})


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
    broadcast_sync("sse:admin", "group_updated", {})
    return serialize_groupe(groupe, include_membres=True, db_session=db)
