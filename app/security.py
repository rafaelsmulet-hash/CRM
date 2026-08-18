"""Hash de senha (Argon2) e sessão (JWT em cookie httpOnly)."""
import datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()

COOKIE_NAME = "jarvis_sessao"
JWT_ALGORITHM = "HS256"


def hash_senha(senha_plana: str) -> str:
    return _hasher.hash(senha_plana)


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha_plana)
    except VerifyMismatchError:
        return False


def gerar_token_sessao(usuario_id: int) -> str:
    settings = get_settings()
    expira_em = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=settings.session_ttl_horas
    )
    payload = {"sub": str(usuario_id), "exp": expira_em}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decodificar_token_sessao(token: str) -> int | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except jwt.PyJWTError:
        return None
