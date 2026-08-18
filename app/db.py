"""Engine e sessão do SQLAlchemy."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

_database_url = get_settings().database_url
# SQLite (uso pessoal, "só Python", sem instalar banco separado) precisa
# disso porque o FastAPI roda rotas síncronas numa threadpool — sem essa
# flag, o driver stdlib reclama de conexão criada numa thread e usada
# noutra. Postgres (psycopg) não precisa e ignora esse parâmetro.
_connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}

engine = create_engine(_database_url, pool_pre_ping=True, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
