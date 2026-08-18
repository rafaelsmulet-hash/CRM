from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import usuario_atual
from app.models import ImportacaoOrbit, Usuario
from app.services import motor, orbit_importer
from app.web.templating import templates

router = APIRouter(prefix="/orbit", tags=["orbit"])


@router.get("/importar")
def form_importar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    historico = db.scalars(select(ImportacaoOrbit).order_by(ImportacaoOrbit.data.desc()).limit(20)).all()
    return templates.TemplateResponse(
        request, "orbit/importar.html", {"usuario": usuario, "ativo": "orbit", "historico": historico}
    )


@router.post("/importar")
async def importar(
    request: Request,
    arquivo: UploadFile,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    conteudo = await arquivo.read()
    try:
        importacao = orbit_importer.importar(
            db, conteudo=conteudo, nome_arquivo=arquivo.filename or "arquivo", usuario_id=usuario.id
        )
        motor.executar(db)
        db.commit()
        contexto = {"usuario": usuario, "ativo": "orbit", "resultado": importacao, "erro_estrutural": None}
    except orbit_importer.ErroEstrutural as exc:
        db.rollback()
        contexto = {"usuario": usuario, "ativo": "orbit", "resultado": None, "erro_estrutural": str(exc)}

    historico = db.scalars(select(ImportacaoOrbit).order_by(ImportacaoOrbit.data.desc()).limit(20)).all()
    contexto["historico"] = historico
    return templates.TemplateResponse(request, "orbit/importar.html", contexto)
