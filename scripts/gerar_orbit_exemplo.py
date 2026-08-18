"""Gera um arquivo .csv de exemplo (dados fictícios) no layout assumido em
config/column_mapping.ini — só para testar o importador localmente. Nunca
use dado real de cliente aqui.
"""
import csv
import datetime
import sys

sys.path.insert(0, ".")

hoje = datetime.date.today()
linhas = [
    {
        "Codigo Cliente": "CLI001",
        "Nome Cliente": "Cliente Exemplo Um",
        "Numero Operacao": "OP-0001",
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
        "Preco Atual Ativo": "32,10",
        "Data Preco": hoje.strftime("%d/%m/%Y"),
    },
    {
        "Codigo Cliente": "CLI002",
        "Nome Cliente": "Cliente Exemplo Dois",
        "Numero Operacao": "OP-0002",
        "Produto": "autocall",
        "Ativo Referencia": "VALE3",
        "Notional": "300000,00",
        "Moeda": "BRL",
        "Data Operacao": (hoje - datetime.timedelta(days=120)).strftime("%d/%m/%Y"),
        "Data Vencimento": (hoje + datetime.timedelta(days=400)).strftime("%d/%m/%Y"),
        "Valor Investido": "300000,00",
        "Barreira Nivel": "70,00",
        "Barreira Tipo": "autocall",
        "Barreira Regra Observacao": "fechamento",
        "Data Fixing": (hoje + datetime.timedelta(days=1)).strftime("%d/%m/%Y"),
        "Tipo Fixing": "autocall",
        "Preco Atual Ativo": "71,20",
        "Data Preco": hoje.strftime("%d/%m/%Y"),
    },
]

with open("data/orbit_exemplo.csv", "w", newline="", encoding="utf-8") as f:
    escritor = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
    escritor.writeheader()
    escritor.writerows(linhas)

print("Gerado: data/orbit_exemplo.csv")
