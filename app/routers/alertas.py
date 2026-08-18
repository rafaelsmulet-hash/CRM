import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import usuario_atual
from app.models import Alerta, Estrutura, Usuario
from app.web.templating import templates

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("")
def listar(
    request: Request,
    mostrar: str = "abertos",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    consulta = select(Alerta).options(joinedload(Alerta.estrutura).joinedload(Estrutura.cliente))
    if mostrar == "abertos":
        consulta = consulta.where(Alerta.resolvido.is_(False))
    alertas = db.scalars(consulta.order_by(Alerta.criado_em.desc()).limit(300)).unique().all()
    return templates.TemplateResponse(
        request, "alertas.html", {"usuario": usuario, "ativo": "alertas", "alertas": alertas, "mostrar": mostrar}
    )


@router.post("/{alerta_id}/resolver")
def resolver(alerta_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    alerta = db.get(Alerta, alerta_id)
    if alerta is not None:
        alerta.resolvido = True
        alerta.lido_por_id = usuario.id
        alerta.lido_em = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)
