import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import usuario_atual
from app.models import (
    Alerta,
    Barreira,
    Estrutura,
    Fixing,
    PanoramaMensal,
    StatusAprovacaoPanorama,
    StatusBarreira,
    StatusEstrutura,
    StatusFixing,
    Usuario,
)
from app.web.templating import templates

router = APIRouter(tags=["dashboard"])

JANELA_FIXING_DIAS = 7
JANELA_VENCIMENTO_DIAS = 30


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    hoje = datetime.date.today()

    total_ativas = db.scalar(
        select(func.count(Estrutura.id)).where(Estrutura.status == StatusEstrutura.ativa)
    )
    barreiras_proximas = db.scalar(
        select(func.count(Barreira.id)).where(Barreira.status_atual == StatusBarreira.proxima)
    )
    barreiras_atingidas = db.scalar(
        select(func.count(Barreira.id)).where(Barreira.status_atual == StatusBarreira.atingida)
    )
    fixings_proximos = db.scalar(
        select(func.count(Fixing.id)).where(
            Fixing.status == StatusFixing.pendente,
            Fixing.data_fixing >= hoje,
            Fixing.data_fixing <= hoje + datetime.timedelta(days=JANELA_FIXING_DIAS),
        )
    )
    vencimentos_proximos = db.scalar(
        select(func.count(Estrutura.id)).where(
            Estrutura.status == StatusEstrutura.ativa,
            Estrutura.data_vencimento >= hoje,
            Estrutura.data_vencimento <= hoje + datetime.timedelta(days=JANELA_VENCIMENTO_DIAS),
        )
    )
    panoramas_pendentes = db.scalar(
        select(func.count(PanoramaMensal.id)).where(
            PanoramaMensal.status_aprovacao == StatusAprovacaoPanorama.rascunho
        )
    )

    alertas_abertos = (
        db.scalars(
            select(Alerta)
            .where(Alerta.resolvido.is_(False))
            .options(joinedload(Alerta.estrutura).joinedload(Estrutura.cliente))
            .order_by(Alerta.criado_em.desc())
            .limit(200)
        )
        .unique()
        .all()
    )
    ordem_severidade = {"critico": 0, "atencao": 1, "info": 2}
    alertas_abertos = sorted(alertas_abertos, key=lambda a: ordem_severidade[a.severidade.value])[:50]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "usuario": usuario,
            "ativo": "dashboard",
            "total_ativas": total_ativas or 0,
            "barreiras_proximas": barreiras_proximas or 0,
            "barreiras_atingidas": barreiras_atingidas or 0,
            "fixings_proximos": fixings_proximos or 0,
            "vencimentos_proximos": vencimentos_proximos or 0,
            "panoramas_pendentes": panoramas_pendentes or 0,
            "alertas_abertos": alertas_abertos,
        },
    )
