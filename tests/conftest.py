"""Fixtures compartilhadas. Roda contra um Postgres real (jarvis_test) —
nada de SQLite: o schema usa tipos ENUM e JSONB nativos do Postgres, e o
objetivo é testar contra o mesmo banco usado em produção.
"""
import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://jarvis:jarvis@localhost:5432/jarvis_test"
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.main import app
from app.models import Papel, Usuario
from app.security import gerar_token_sessao, hash_senha


@pytest.fixture(scope="session", autouse=True)
def _preparar_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db_session():
    conexao = engine.connect()
    transacao = conexao.begin()
    sessao = Session(bind=conexao, join_transaction_mode="create_savepoint")
    yield sessao
    sessao.close()
    transacao.rollback()
    conexao.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def usuario_admin(db_session) -> Usuario:
    usuario = Usuario(
        nome="Admin Teste",
        email="admin@teste.local",
        senha_hash=hash_senha("senha-teste"),
        papel=Papel.admin,
        ativo=True,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


@pytest.fixture()
def client_autenticado(client, usuario_admin):
    token = gerar_token_sessao(usuario_admin.id)
    client.cookies.set("jarvis_sessao", token)
    return client
