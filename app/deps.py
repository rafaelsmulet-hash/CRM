"""Dependências do FastAPI: sessão de banco, usuário logado, RBAC."""
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Papel, Usuario
from app.security import COOKIE_NAME, decodificar_token_sessao


class RedirecionarParaLogin(HTTPException):
    """Erro especial: em vez de um 401 puro, a página de login é exibida."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_303_SEE_OTHER)


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    token = request.cookies.get(COOKIE_NAME)
    usuario_id = decodificar_token_sessao(token) if token else None
    if usuario_id is None:
        raise RedirecionarParaLogin()
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        raise RedirecionarParaLogin()
    return usuario


def requer_papel(*papeis_permitidos: Papel) -> Callable[[Usuario], Usuario]:
    def checar(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if usuario.papel not in papeis_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Ação restrita a: {', '.join(p.value for p in papeis_permitidos)}.",
            )
        return usuario

    return checar
