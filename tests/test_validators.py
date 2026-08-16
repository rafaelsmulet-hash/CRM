import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.validators import (  # noqa: E402
    LinhaInvalidaError, extrair_linha, gerar_operacao_ref_sintetico,
    parse_data, parse_numero, validar_colunas_presentes,
)

MAPEAMENTO = {
    "cliente_id": "cliente_id", "nome": "nome", "tipo_estrutura": "tipo_estrutura",
    "ativo_objeto": "ativo_objeto", "data_fechamento": "data_fechamento",
    "data_vencimento": "data_vencimento", "operacao_id": "operacao_id",
    "strike_1": "strike_1", "strike_2": "strike_2", "barreira": "barreira",
    "status_barreira": "status_barreira", "valor_notional": "valor_notional",
    "perfil_suitability": "perfil_suitability",
}


class TestParseData(unittest.TestCase):
    def test_formato_br(self):
        self.assertEqual(parse_data("16/08/2026", "%d/%m/%Y"), date(2026, 8, 16))

    def test_fallback_iso(self):
        self.assertEqual(parse_data("2026-08-16", "%d/%m/%Y"), date(2026, 8, 16))

    def test_vazio_retorna_none(self):
        self.assertIsNone(parse_data("", "%d/%m/%Y"))

    def test_invalido_retorna_none(self):
        self.assertIsNone(parse_data("não é uma data", "%d/%m/%Y"))


class TestParseNumero(unittest.TestCase):
    def test_formato_br_com_milhar(self):
        self.assertEqual(parse_numero("1.234.567,89", ","), 1234567.89)

    def test_formato_br_sem_milhar(self):
        self.assertEqual(parse_numero("1234,56", ","), 1234.56)

    def test_formato_internacional(self):
        self.assertEqual(parse_numero("1,234,567.89", "."), 1234567.89)

    def test_vazio_retorna_none(self):
        self.assertIsNone(parse_numero("", ","))

    def test_invalido_levanta_erro(self):
        with self.assertRaises(ValueError):
            parse_numero("abc", ",")


class TestOperacaoRefSintetico(unittest.TestCase):
    def test_deterministico(self):
        ref1 = gerar_operacao_ref_sintetico("C1", "autocall", "PETR4", "2026-01-01", "10", "20", "30")
        ref2 = gerar_operacao_ref_sintetico("C1", "autocall", "PETR4", "2026-01-01", "10", "20", "30")
        self.assertEqual(ref1, ref2)

    def test_muda_com_input(self):
        ref1 = gerar_operacao_ref_sintetico("C1", "autocall", "PETR4", "2026-01-01", "10", "20", "30")
        ref2 = gerar_operacao_ref_sintetico("C1", "autocall", "PETR4", "2026-01-02", "10", "20", "30")
        self.assertNotEqual(ref1, ref2)


class TestValidarColunasPresentes(unittest.TestCase):
    def test_todas_presentes(self):
        colunas = list(MAPEAMENTO.values())
        self.assertEqual(validar_colunas_presentes(colunas, MAPEAMENTO), [])

    def test_coluna_obrigatoria_faltando(self):
        colunas = [c for c in MAPEAMENTO.values() if c != "data_vencimento"]
        faltando = validar_colunas_presentes(colunas, MAPEAMENTO)
        self.assertEqual(len(faltando), 1)
        self.assertIn("data_vencimento", faltando[0])


class TestExtrairLinha(unittest.TestCase):
    def _linha_valida(self, **overrides):
        base = {
            "cliente_id": "C1", "nome": "Fulano de Tal", "tipo_estrutura": "Autocall",
            "ativo_objeto": "PETR4", "data_fechamento": "01/01/2026", "data_vencimento": "01/01/2027",
            "operacao_id": "OP1", "strike_1": "30,50", "strike_2": "", "barreira": "25,00",
            "status_barreira": "nao_observada", "valor_notional": "1.000.000,00",
            "perfil_suitability": "agressivo",
        }
        base.update(overrides)
        return base

    def test_linha_valida_completa(self):
        registro, avisos = extrair_linha(self._linha_valida(), MAPEAMENTO, "%d/%m/%Y", ",")
        self.assertEqual(registro["cliente_id"], "C1")
        self.assertEqual(registro["data_fechamento"], date(2026, 1, 1))
        self.assertEqual(registro["strike_1"], 30.5)
        self.assertIsNone(registro["strike_2"])
        self.assertEqual(avisos, [])

    def test_campo_obrigatorio_ausente_levanta_erro(self):
        with self.assertRaises(LinhaInvalidaError):
            extrair_linha(self._linha_valida(nome=""), MAPEAMENTO, "%d/%m/%Y", ",")

    def test_data_invalida_levanta_erro(self):
        with self.assertRaises(LinhaInvalidaError):
            extrair_linha(self._linha_valida(data_vencimento="não é data"), MAPEAMENTO, "%d/%m/%Y", ",")

    def test_operacao_id_ausente_gera_sintetico_com_aviso(self):
        registro, avisos = extrair_linha(self._linha_valida(operacao_id=""), MAPEAMENTO, "%d/%m/%Y", ",")
        self.assertTrue(registro["operacao_id"].startswith("SINT-"))
        self.assertEqual(len(avisos), 1)

    def test_numero_invalido_em_campo_opcional_nao_derruba_linha(self):
        registro, avisos = extrair_linha(self._linha_valida(barreira="abc"), MAPEAMENTO, "%d/%m/%Y", ",")
        self.assertIsNone(registro["barreira"])
        self.assertEqual(len(avisos), 1)


if __name__ == "__main__":
    unittest.main()
