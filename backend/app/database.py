from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Configuration de la base de données.
# pool_pre_ping : valide la connexion avant chaque checkout. Sans lui, un
# redémarrage de Postgres laisse des connexions mortes dans le pool et les N
# requêtes suivantes lèvent OperationalError avant que SQLAlchemy ne reconnecte.
# pool_recycle : recycle la connexion avant que Postgres ou un firewall ne coupe
# une session restée trop longtemps inactive.
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
