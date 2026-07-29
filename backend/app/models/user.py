import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    prenom = Column(String(100), nullable=True)
    nom = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="USER")
    departement = Column(String(50), nullable=True)
    is_gestionnaire = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    groupes = relationship(
        "Groupe",
        secondary="user_groups",
        backref="membres",
        lazy="select",
    )
