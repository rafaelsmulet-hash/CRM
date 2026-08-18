"""Lista/detalhe de estruturas, e cadastro manual (via secundária, exceção)."""
import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import usuario_atual
from app.models import Barreira, Cliente, Estrutura, PrecoMercado, StatusBarreira, StatusEstrutura, Usuario
from app.services import auditoria
from app.services.regras import calcular_distancia_pct
from app.web.templating import templates

router = APIRouter(prefix="/estruturas", tags=["estruturas"])


@router.get("")
def listar(
    request: Request,
    cliente_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    consulta = select(Estrutura).options(
        joinedload(Estrutura.cliente), joinedload(Estrutura.barreiras)
    )
    if cliente_id:
        consulta = consulta.where(Estrutura.cliente_id == cliente_id)
    if status:
        consulta = consulta.where(Estrutura.status == status)
    estruturas = db.scalars(consulta.order_by(Estrutura.data_vencimento)).unique().all()
    return templates.TemplateResponse(
        request,
        "estruturas/lista.html",
        {"usuario": usuario, "ativo": "estruturas", "estruturas": estruturas},
    )


@router.get("/novo")
def form_novo(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    clientes = db.scalars(select(Cliente).order_by(Cliente.nome)).all()
    return templates.TemplateResponse(
        request, "estruturas/form.html", {"usuario": usuario, "ativo": "estruturas", "clientes": clientes}
    )


@router.post("/novo")
def criar(
    request: Request,
    cliente_id: int = Form(...),
    operacao_ref: str = Form(...),
    tipo_estrutura: str = Form(...),
    ativo_principal: str = Form(...),
    notional: str = Form(""),
    data_inicio: str = Form(...),
    data_vencimento: str = Form(...),
    barreira_nivel: str = Form(""),
    barreira_direcao: str = Form("queda"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    estrutura = Estrutura(
        cliente_id=cliente_id,
        operacao_ref=operacao_ref.strip(),
        tipo_estrutura=tipo_estrutura.strip(),
        ativo_principal=ativo_principal.strip().upper(),
        notional=float(notional) if notional else None,
        data_inicio=datetime.date.fromisoformat(data_inicio),
        data_vencimento=datetime.date.fromisoformat(data_vencimento),
        status=StatusEstrutura.ativa,
        fonte_importacao="manual",
        criado_por_id=usuario.id,
        atualizado_por_id=usuario.id,
    )
    db.add(estrutura)
    db.flush()

    if barreira_nivel:
        db.add(
            Barreira(
                estrutura_id=estrutura.id,
                tipo="protecao",
                nivel=float(barreira_nivel),
                direcao=barreira_direcao,
                ativo_referencia=estrutura.ativo_principal,
                status_atual=StatusBarreira.normal,
            )
        )

    auditoria.registrar_criacao(
        db,
        tabela="estruturas",
        registro_id=estrutura.id,
        usuario_id=usuario.id,
        campos={
            "operacao_ref": estrutura.operacao_ref,
            "tipo_estrutura": estrutura.tipo_estrutura,
            "cliente_id": cliente_id,
            "fonte": "manual",
        },
    )
    db.commit()
    return RedirectResponse(url=f"/estruturas/{estrutura.id}", status_code=303)


@router.get("/{estrutura_id}")
def detalhe(
    request: Request,
    estrutura_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    estrutura = db.get(
        Estrutura,
        estrutura_id,
        options=[
            joinedload(Estrutura.cliente),
            joinedload(Estrutura.barreiras),
            joinedload(Estrutura.fixings),
            joinedload(Estrutura.eventos),
        ],
    )

    distancias: dict[int, float | None] = {}
    for barreira in estrutura.barreiras:
        ultimo_preco = db.scalar(
            select(PrecoMercado)
            .where(PrecoMercado.ticker == barreira.ativo_referencia)
            .order_by(PrecoMercado.data.desc())
            .limit(1)
        )
        distancias[barreira.id] = (
            calcular_distancia_pct(float(ultimo_preco.preco), float(barreira.nivel))
            if ultimo_preco
            else None
        )

    return templates.TemplateResponse(
        request,
        "estruturas/detalhe.html",
        {"usuario": usuario, "ativo": "estruturas", "estrutura": estrutura, "distancias": distancias},
    )
