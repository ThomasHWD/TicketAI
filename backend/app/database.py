from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# pool_pre_ping prevents stale connections after a Postgres restart from raising OperationalError.
# pool_recycle prevents idle-session cuts by Postgres or a firewall.
engine = create_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
