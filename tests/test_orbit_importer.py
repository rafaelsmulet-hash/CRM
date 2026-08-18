import csv
import datetime
import io

from sqlalchemy import select

from app.models import Estrutura, StatusBarreira, StatusEstrutura
from app.services import motor, orbit_importer

CABECALHO = [
    "Codigo Cliente", "Nome Cliente", "Numero Operacao", "Produto", "Ativo Referencia",
    "Notional", "Moeda", "Data Operacao", "Data Vencimento", "Valor Investido",
    "Barreira Nivel", "Barreira Tipo", "Barreira Regra Observacao",
    "Data Fixing", "Tipo Fixing", "Preco Atual Ativo", "Data Preco",
]


def _linha(**over) -> dict:
    hoje = datetime.date.today()
    base = {
        "Codigo Cliente": "CLI001",
        "Nome Cliente": "Cliente Um",
        "Numero Operacao": "OP-0001",
        "Produto": "capital_protegido",
        "Ativo Referencia": "PETR4",
        "Notional": "500000,00",
        "Moeda": "BRL",
        "Data Operacao": (hoje - datetime.timedelta(days=60)).strftime("%d/%m/%Y"),
        "Data Vencimento": (hoje + datetime.timedelta(days=300)).strftime("%d/%m/%Y"),
        "Valor Investido": "500000,00",
        "Barreira Nivel": "31,00",
        "Barreira Tipo": "protecao",
        "Barreira Regra Observacao": "fechamento",
        "Data Fixing": "",
        "Tipo Fixing": "",
        "Preco Atual Ativo": "32,10",
        "Data Preco": hoje.strftime("%d/%m/%Y"),
    }
    base.update(over)
    return base


def _csv_bytes(linhas: list[dict]) -> bytes:
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=CABECALHO)
    escritor.writeheader()
    escritor.writerows(linhas)
    return buffer.getvalue().encode("utf-8")


def test_import_cria_cliente_estrutura_barreira_e_preco(db_session, usuario_admin):
    conteudo = _csv_bytes([_linha()])
    resultado = orbit_importer.importar(
        db_session, conteudo=conteudo, nome_arquivo="orbit.csv", usuario_id=usuario_admin.id
    )
    db_session.flush()

    assert resultado.novas == 1
    assert resultado.atualizadas == 0
    assert not resultado.erros

    estrutura = db_session.scalar(select(Estrutura).where(Estrutura.operacao_ref == "OP-0001"))
    assert estrutura is not None
    assert estrutura.cliente.nome == "Cliente Um"
    assert estrutura.status == StatusEstrutura.ativa
    assert estrutura.fonte_importacao == "orbit"
    assert len(estrutura.barreiras) == 1
    assert float(estrutura.barreiras[0].nivel) == 31.00


def test_reimportar_mesma_operacao_atualiza_em_vez_de_duplicar(db_session, usuario_admin):
    orbit_importer.importar(
        db_session, conteudo=_csv_bytes([_linha()]), nome_arquivo="a.csv", usuario_id=usuario_admin.id
    )
    db_session.flush()

    resultado2 = orbit_importer.importar(
        db_session,
        conteudo=_csv_bytes([_linha(**{"Preco Atual Ativo": "30,00"})]),
        nome_arquivo="b.csv",
        usuario_id=usuario_admin.id,
    )
    db_session.flush()

    assert resultado2.novas == 0
    assert resultado2.atualizadas == 1
    total = db_session.scalar(select(Estrutura).where(Estrutura.operacao_ref == "OP-0001"))
    assert total is not None


def test_operacao_ausente_na_reimportacao_e_encerrada(db_session, usuario_admin):
    orbit_importer.importar(
        db_session, conteudo=_csv_bytes([_linha()]), nome_arquivo="a.csv", usuario_id=usuario_admin.id
    )
    db_session.flush()

    resultado2 = orbit_importer.importar(
        db_session,
        conteudo=_csv_bytes([_linha(**{"Numero Operacao": "OP-9999"})]),
        nome_arquivo="b.csv",
        usuario_id=usuario_admin.id,
    )
    db_session.flush()

    assert resultado2.encerradas == 1
    op1 = db_session.scalar(select(Estrutura).where(Estrutura.operacao_ref == "OP-0001"))
    assert op1.status == StatusEstrutura.encerrada


def test_motor_marca_barreira_atingida_apos_import(db_session, usuario_admin):
    orbit_importer.importar(
        db_session,
        conteudo=_csv_bytes([_linha(**{"Preco Atual Ativo": "28,00"})]),  # abaixo do nível 31,00
        nome_arquivo="a.csv",
        usuario_id=usuario_admin.id,
    )
    db_session.flush()

    motor.executar(db_session)
    db_session.flush()

    estrutura = db_session.scalar(select(Estrutura).where(Estrutura.operacao_ref == "OP-0001"))
    assert estrutura.barreiras[0].status_atual == StatusBarreira.atingida
    assert len(estrutura.eventos) == 1
    assert estrutura.eventos[0].status_novo == "atingida"
