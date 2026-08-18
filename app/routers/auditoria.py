from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import requer_papel
from app.models import AuditLog, Papel, Usuario
from app.web.templating import templates

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("")
def listar(
    request: Request,
    tabela: str | None = None,
    registro_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requer_papel(Papel.compliance, Papel.admin)),
):
    consulta = select(AuditLog)
    if tabela:
        consulta = consulta.where(AuditLog.tabela == tabela)
    if registro_id:
        consulta = consulta.where(AuditLog.registro_id == registro_id)
    registros = db.scalars(consulta.order_by(AuditLog.data_hora.desc()).limit(500)).all()

    usuarios_por_id = {u.id: u for u in db.scalars(select(Usuario)).all()}

    return templates.TemplateResponse(
        request,
        "auditoria.html",
        {
            "usuario": usuario,
            "ativo": "auditoria",
            "registros": registros,
            "usuarios_por_id": usuarios_por_id,
            "tabela": tabela or "",
        },
    )
