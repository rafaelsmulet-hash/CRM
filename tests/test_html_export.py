import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.html_export import gerar_html_painel  # noqa: E402

DADOS_BASE = {
    "data": "2026-08-17",
    "pendentes": 3,
    "janela_vencimento_dias": 15,
    "vencimentos_proximos": [
        {"cliente_nome": "Maria Cliente", "cliente_codigo": "1002", "tipo_estrutura": "Autocall",
         "ativo_objeto": "PETR4", "data_vencimento": "2026-08-26", "dias_restantes": 9},
    ],
    "valores_barreira_tocada": ["tocada", "rompida"],
    "barreiras_tocadas": [],
    "janela_sem_contato_dias": 30,
    "janela_sem_contato_ativa": True,
    "clientes_sem_contato": [],
}


class TestGerarHtmlPainel(unittest.TestCase):
    def test_gera_html_valido_com_conteudo(self):
        html = gerar_html_painel(DADOS_BASE)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("2026-08-17", html)
        self.assertIn("Maria Cliente", html)
        self.assertIn("PETR4", html)

    def test_secoes_vazias_nao_quebram(self):
        html = gerar_html_painel(DADOS_BASE)
        self.assertIn("Nenhum item.", html)  # barreiras_tocadas e clientes_sem_contato vazios

    def test_escapa_caracteres_html_nos_dados(self):
        dados = dict(DADOS_BASE)
        dados["vencimentos_proximos"] = [
            {"cliente_nome": "<script>alert(1)</script>", "cliente_codigo": "1", "tipo_estrutura": "X",
             "ativo_objeto": "Y", "data_vencimento": "2026-08-26", "dias_restantes": 1},
        ]
        html = gerar_html_painel(dados)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
