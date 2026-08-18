"""Trilha de auditoria de cadastro — quem alterou o quê, quando, de/para.

Escrita sempre pela camada de serviço, nunca direto pelas rotas — garante que
toda mutação de cliente/estrutura passa pelo mesmo ponto de registro (seção
10 da arquitetura aprovada).
"""
from sqlalchemy.orm import Session

from app.models import AcaoAuditoria, AuditLog


def registrar(
    db: Session,
    *,
    tabela: str,
    registro_id: int,
    usuario_id: int | None,
    campo: str,
    valor_anterior: object,
    valor_novo: object,
    acao: AcaoAuditoria,
) -> None:
    db.add(
        AuditLog(
            tabela=tabela,
            registro_id=registro_id,
            usuario_id=usuario_id,
            campo=campo,
            valor_anterior=None if valor_anterior is None else str(valor_anterior),
            valor_novo=None if valor_novo is None else str(valor_novo),
            acao=acao,
        )
    )


def registrar_criacao(
    db: Session, *, tabela: str, registro_id: int, usuario_id: int | None, campos: dict
) -> None:
    for campo, valor in campos.items():
        registrar(
            db,
            tabela=tabela,
            registro_id=registro_id,
            usuario_id=usuario_id,
            campo=campo,
            valor_anterior=None,
            valor_novo=valor,
            acao=AcaoAuditoria.insert,
        )


def registrar_alteracoes(
    db: Session,
    *,
    tabela: str,
    registro_id: int,
    usuario_id: int | None,
    valores_anteriores: dict,
    valores_novos: dict,
) -> bool:
    """Compara campo a campo e só grava o que de fato mudou. Retorna se algo mudou."""
    houve_mudanca = False
    for campo, novo in valores_novos.items():
        anterior = valores_anteriores.get(campo)
        if anterior != novo:
            houve_mudanca = True
            registrar(
                db,
                tabela=tabela,
                registro_id=registro_id,
                usuario_id=usuario_id,
                campo=campo,
                valor_anterior=anterior,
                valor_novo=novo,
                acao=AcaoAuditoria.update,
            )
    return houve_mudanca
