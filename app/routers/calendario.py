import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import usuario_atual
from app.models import Estrutura, Fixing, StatusEstrutura, StatusFixing, Usuario
from app.web.templating import templates

router = APIRouter(prefix="/calendario", tags=["calendario"])

JANELA_DIAS = 45


@router.get("")
def calendario(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    hoje = datetime.date.today()
    limite = hoje + datetime.timedelta(days=JANELA_DIAS)

    fixings = (
        db.scalars(
            select(Fixing)
            .where(
                Fixing.status == StatusFixing.pendente,
                Fixing.data_fixing >= hoje,
                Fixing.data_fixing <= limite,
            )
            .options(joinedload(Fixing.estrutura).joinedload(Estrutura.cliente))
            .order_by(Fixing.data_fixing)
        )
        .unique()
        .all()
    )

    vencimentos = (
        db.scalars(
            select(Estrutura)
            .where(
                Estrutura.status == StatusEstrutura.ativa,
                Estrutura.data_vencimento >= hoje,
                Estrutura.data_vencimento <= limite,
            )
            .options(joinedload(Estrutura.cliente))
            .order_by(Estrutura.data_vencimento)
        )
        .unique()
        .all()
    )

    eventos = sorted(
        [{"data": f.data_fixing, "tipo": "Fixing", "obj": f} for f in fixings]
        + [{"data": e.data_vencimento, "tipo": "Vencimento", "obj": e} for e in vencimentos],
        key=lambda x: x["data"],
    )

    return templates.TemplateResponse(
        request,
        "calendario.html",
        {"usuario": usuario, "ativo": "calendario", "eventos": eventos, "janela_dias": JANELA_DIAS},
    )
