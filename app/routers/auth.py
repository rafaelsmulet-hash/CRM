from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Usuario
from app.security import COOKIE_NAME, gerar_token_sessao, verificar_senha
from app.web.templating import templates

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def form_login(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = db.scalar(select(Usuario).where(Usuario.email == email.strip().lower()))
    if usuario is None or not usuario.ativo or not verificar_senha(senha, usuario.senha_hash):
        return templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha inválidos."}, status_code=401
        )

    token = gerar_token_sessao(usuario.id)
    resposta = RedirectResponse(url="/", status_code=303)
    resposta.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return resposta


@router.post("/logout")
def logout():
    resposta = RedirectResponse(url="/auth/login", status_code=303)
    resposta.delete_cookie(COOKIE_NAME)
    return resposta
