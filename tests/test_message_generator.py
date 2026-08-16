import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from templates.message_generator import carregar_templates, gerar_mensagem  # noqa: E402


class TestGerarMensagem(unittest.TestCase):
    def setUp(self):
        self.templates = carregar_templates()
        self.operacao_base = dict(
            cliente_nome="Fulano de Tal", cliente_codigo="C1", tipo_estrutura="Autocall",
            ativo_objeto="PETR4", data_fechamento="2026-01-01", data_vencimento="2027-01-01",
            strike_1=30.5, strike_2=None, barreira=25.0, status_barreira="tocada", valor_notional=1000000.0,
        )

    def test_usa_template_especifico_por_tipo_estrutura(self):
        msg = gerar_mensagem(self.operacao_base, "teste", 10, templates=self.templates)
        self.assertIn("Autocall", msg)
        self.assertIn("PETR4", msg)
        self.assertIn("barreira em 25.0", msg)

    def test_usa_default_para_tipo_desconhecido(self):
        op = dict(self.operacao_base, tipo_estrutura="Estrutura Nova Sem Template")
        msg = gerar_mensagem(op, "teste", 10, templates=self.templates)
        self.assertIn("Estrutura Nova Sem Template", msg)

    def test_campo_ausente_vira_nd(self):
        op = dict(self.operacao_base, valor_notional=None, tipo_estrutura="Capital Protegido")
        msg = gerar_mensagem(op, "teste", 10, templates=self.templates)
        self.assertIn("N/D", msg)

    def test_determinismo(self):
        msg1 = gerar_mensagem(self.operacao_base, "motivo X", 5, templates=self.templates)
        msg2 = gerar_mensagem(self.operacao_base, "motivo X", 5, templates=self.templates)
        self.assertEqual(msg1, msg2)

    def test_placeholder_desconhecido_nao_quebra(self):
        templates = dict(self.templates)
        templates["default"] = "Olá {nome}, campo inexistente: {campo_que_nao_existe}"
        op = dict(self.operacao_base, tipo_estrutura="tipo_sem_template")
        msg = gerar_mensagem(op, "motivo", 1, templates=templates)
        self.assertIn("[campo_que_nao_existe?]", msg)


if __name__ == "__main__":
    unittest.main()
