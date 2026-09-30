import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ReponseChunk(Base):
    __tablename__ = "reponse_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reponse_id = Column(UUID(as_uuid=True), ForeignKey("reponses.id"), nullable=False)
    doc_id = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    # document version the index refers to — after an update, the same index names another passage. NULL = legacy
    # row of unknown version, matched by index as before.
    version = Column(Integer, nullable=True)
    score_cosinus = Column(Float, nullable=True)
    rerank_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reponse = relationship("Reponse", back_populates="chunks")
