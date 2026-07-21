"""Seed des validateurs de développement.

Insère (de façon idempotente) les utilisateurs fictifs utilisés par le
sélecteur de validateur du front (shim d'identité, en attendant la vraie
authentification). Nécessaire car `tickets.locked_by` et `reponses.validator_id`
référencent `users.id` : sans ces lignes, verrouiller ou valider échoue.

Usage :
    python -m scripts.seed_validators
"""

import uuid

from app.database import SessionLocal
from app.models.user import User

VALIDATEURS = [
    ("00000000-0000-0000-0000-000000000001", "validateur.a@entreprise.fr"),
    ("00000000-0000-0000-0000-000000000002", "validateur.b@entreprise.fr"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        for id_str, email in VALIDATEURS:
            uid = uuid.UUID(id_str)
            if db.query(User).filter(User.id == uid).first():
                print(f"= {email} existe déjà.")
                continue
            db.add(User(id=uid, email=email, role="VALIDATOR"))
            print(f"+ {email} créé.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
