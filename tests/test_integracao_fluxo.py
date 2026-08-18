"""Fluxo completo via HTTP: import Orbit -> motor -> dashboard -> panorama -> aprovação.

Mesmo golden path validado manualmente durante a construção (seção 11 do
README), agora automatizado.
"""
import csv
import datetime
import io


def _csv_exemplo() -> bytes:
    hoje = datetime.date.today()
    cabecalho = [
        "Codigo Cliente", "Nome Cliente", "Numero Operacao", "Produto", "Ativo Referencia",
        "Notional", "Moeda", "Data Operacao", "Data Vencimento", "Valor Investido",
        "Barreira Nivel", "Barreira Tipo", "Barreira Regra Observacao",
        "Data Fixing", "Tipo Fixing", "Preco Atual Ativo", "Data Preco",
    ]
    linha = {
        "Codigo Cliente": "CLI001",
        "Nome Cliente": "Cliente Integração",
        "Numero Operacao": "OP-INT-1",
        "Produto": "capital_protegido",
        "Ativo Referencia": "PETR4",
        "Notional": "500000,00",
        "Moeda": "BRL",
        "Data Operacao": (hoje - datetime.timedelta(days=60)).strftime("%d/%m/%Y"),
        "Data Vencimento": (hoje + datetime.timedelta(days=10)).strftime("%d/%m/%Y"),
        "Valor Investido": "500000,00",
        "Barreira Nivel": "31,00",
        "Barreira Tipo": "protecao",
        "Barreira Regra Observacao": "fechamento",
        "Data Fixing": (hoje + datetime.timedelta(days=3)).strftime("%d/%m/%Y"),
        "Tipo Fixing": "cupom",
        "Preco Atual Ativo": "28,00",  # abaixo do nível -> barreira atingida
        "Data Preco": hoje.strftime("%d/%m/%Y"),
    }
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=cabecalho)
    escritor.writeheader()
    escritor.writerow(linha)
    return buffer.getvalue().encode("utf-8")


def test_fluxo_completo_import_motor_dashboard_panorama(client_autenticado):
    resposta_import = client_autenticado.post(
        "/orbit/importar",
        files={"arquivo": ("orbit.csv", _csv_exemplo(), "text/csv")},
    )
    assert resposta_import.status_code == 200
    assert "Importado com sucesso" in resposta_import.text
    assert "1 nova(s)" in resposta_import.text

    dashboard = client_autenticado.get("/")
    assert "Atenção hoje" in dashboard.text
    assert "barreira" in dashboard.text.lower()
    assert "atingida" in dashboard.text.lower()

    estruturas = client_autenticado.get("/estruturas")
    assert "OP-INT-1" in estruturas.text

    gerar = client_autenticado.post("/panoramas/gerar", follow_redirects=False)
    assert gerar.status_code == 303

    panoramas = client_autenticado.get("/panoramas?status=rascunho")
    assert "OP-INT-1" in panoramas.text

    auditoria = client_autenticado.get("/auditoria")
    assert "estruturas" in auditoria.text


def test_login_com_senha_errada_mostra_erro(client, usuario_admin):
    resposta = client.post("/auth/login", data={"email": usuario_admin.email, "senha": "errada"})
    assert resposta.status_code == 401
    assert "inválidos" in resposta.text


def test_pagina_protegida_sem_login_redireciona(client):
    resposta = client.get("/", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/auth/login"
