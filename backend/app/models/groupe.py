import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.schema import PrimaryKeyConstraint

from app.database import Base

user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")),
    Column("groupe_id", UUID(as_uuid=True), ForeignKey("groupes.id", ondelete="CASCADE")),
    Column("is_chef", Boolean, nullable=False, server_default="false"),
    PrimaryKeyConstraint("user_id", "groupe_id"),
)


class Groupe(Base):
    __tablename__ = "groupes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom = Column(String(100), nullable=False)
    domaine = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("domaine", name="uq_groupe_domaine"),)
