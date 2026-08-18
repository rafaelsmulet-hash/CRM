"""Cadastro manual de cliente — via secundária, para exceções fora do Orbit."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import usuario_atual
from app.models import Cliente, Usuario
from app.services import auditoria
from app.web.templating import templates

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("")
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    clientes = db.scalars(select(Cliente).order_by(Cliente.nome)).all()
    return templates.TemplateResponse(
        request, "clientes/lista.html", {"usuario": usuario, "ativo": "estruturas", "clientes": clientes}
    )


@router.get("/novo")
def form_novo(request: Request, usuario: Usuario = Depends(usuario_atual)):
    return templates.TemplateResponse(
        request, "clientes/form.html", {"usuario": usuario, "ativo": "estruturas", "cliente": None}
    )


@router.post("/novo")
def criar(
    request: Request,
    nome: str = Form(...),
    suitability: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    cliente = Cliente(
        nome=nome.strip(),
        suitability=suitability.strip() or None,
        sales_trader_responsavel_id=usuario.id,
        criado_por_id=usuario.id,
        atualizado_por_id=usuario.id,
    )
    db.add(cliente)
    db.flush()
    auditoria.registrar_criacao(
        db,
        tabela="clientes",
        registro_id=cliente.id,
        usuario_id=usuario.id,
        campos={"nome": cliente.nome, "suitability": cliente.suitability, "fonte": "manual"},
    )
    db.commit()
    return RedirectResponse(url="/clientes", status_code=303)
