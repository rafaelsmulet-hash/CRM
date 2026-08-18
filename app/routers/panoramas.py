import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import usuario_atual
from app.models import Estrutura, PanoramaMensal, StatusAprovacaoPanorama, StatusEstrutura, Usuario
from app.services import panorama as panorama_service
from app.web.templating import templates

router = APIRouter(prefix="/panoramas", tags=["panoramas"])


@router.get("")
def listar(
    request: Request,
    status: str = "rascunho",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    consulta = select(PanoramaMensal).options(
        joinedload(PanoramaMensal.cliente), joinedload(PanoramaMensal.estrutura)
    )
    if status != "todos":
        consulta = consulta.where(PanoramaMensal.status_aprovacao == status)
    panoramas = db.scalars(consulta.order_by(PanoramaMensal.criado_em.desc())).unique().all()
    return templates.TemplateResponse(
        request, "panoramas/lista.html", {"usuario": usuario, "ativo": "panoramas", "panoramas": panoramas, "status": status}
    )


@router.post("/gerar")
def gerar(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Gera (ou regenera, se ainda rascunho) o panorama do mês corrente para toda estrutura ativa."""
    competencia = datetime.date.today().strftime("%Y-%m")
    estruturas = (
        db.scalars(
            select(Estrutura)
            .where(Estrutura.status == StatusEstrutura.ativa)
            .options(joinedload(Estrutura.cliente), joinedload(Estrutura.barreiras))
        )
        .unique()
        .all()
    )

    for estrutura in estruturas:
        existente = db.scalar(
            select(PanoramaMensal).where(
                PanoramaMensal.estrutura_id == estrutura.id, PanoramaMensal.competencia == competencia
            )
        )
        texto = panorama_service.gerar_texto(db, estrutura, competencia)
        if existente is None:
            db.add(
                PanoramaMensal(
                    cliente_id=estrutura.cliente_id,
                    estrutura_id=estrutura.id,
                    competencia=competencia,
                    conteudo_gerado=texto,
                    status_aprovacao=StatusAprovacaoPanorama.rascunho,
                )
            )
        elif existente.status_aprovacao == StatusAprovacaoPanorama.rascunho:
            existente.conteudo_gerado = texto  # regenera só o que ainda não foi decidido

    db.commit()
    return RedirectResponse(url="/panoramas", status_code=303)


@router.get("/{panorama_id}")
def detalhe(
    request: Request,
    panorama_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    p = db.get(PanoramaMensal, panorama_id, options=[joinedload(PanoramaMensal.cliente), joinedload(PanoramaMensal.estrutura)])
    return templates.TemplateResponse(
        request, "panoramas/detalhe.html", {"usuario": usuario, "ativo": "panoramas", "p": p}
    )


@router.post("/{panorama_id}/aprovar")
def aprovar(
    panorama_id: int,
    conteudo_final: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    p = db.get(PanoramaMensal, panorama_id)
    p.conteudo_final = conteudo_final
    p.status_aprovacao = StatusAprovacaoPanorama.aprovado
    p.aprovado_por_id = usuario.id
    p.aprovado_em = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return RedirectResponse(url="/panoramas", status_code=303)


@router.post("/{panorama_id}/rejeitar")
def rejeitar(panorama_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    p = db.get(PanoramaMensal, panorama_id)
    p.status_aprovacao = StatusAprovacaoPanorama.rejeitado
    p.aprovado_por_id = usuario.id
    p.aprovado_em = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return RedirectResponse(url="/panoramas", status_code=303)
