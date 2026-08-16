import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rules.rules_definitions import (  # noqa: E402
    avaliar_evento_barreira, avaliar_tempo_decorrido, avaliar_vencimento_proximo, meses_decorridos,
)


class TestMesesDecorridos(unittest.TestCase):
    def test_meses_exatos(self):
        self.assertEqual(meses_decorridos(date(2026, 1, 10), date(2026, 4, 10)), 3)

    def test_ainda_nao_completou_o_mes(self):
        self.assertEqual(meses_decorridos(date(2026, 1, 10), date(2026, 4, 9)), 2)

    def test_mesmo_dia_fechamento(self):
        self.assertEqual(meses_decorridos(date(2026, 1, 10), date(2026, 1, 10)), 0)

    def test_nunca_negativo(self):
        self.assertEqual(meses_decorridos(date(2026, 5, 1), date(2026, 4, 1)), 0)


class TestTempoDecorrido(unittest.TestCase):
    def test_dispara_limiares_atingidos(self):
        disparos = avaliar_tempo_decorrido(date(2026, 1, 1), date(2026, 7, 1), [1, 3, 6, 12])
        regras = [r for r, _ in disparos]
        self.assertEqual(regras, ["tempo_decorrido_1m", "tempo_decorrido_3m", "tempo_decorrido_6m"])

    def test_nenhum_limiar_atingido(self):
        disparos = avaliar_tempo_decorrido(date(2026, 6, 25), date(2026, 7, 1), [1, 3, 6, 12])
        self.assertEqual(disparos, [])


class TestVencimentoProximo(unittest.TestCase):
    def test_dispara_dentro_do_limite(self):
        disparos, dias = avaliar_vencimento_proximo(date(2026, 8, 20), date(2026, 8, 16), [30, 15, 5])
        self.assertEqual(dias, 4)
        regras = [r for r, _ in disparos]
        self.assertEqual(regras, ["vencimento_5d", "vencimento_15d", "vencimento_30d"])

    def test_fora_do_limite_nao_dispara(self):
        disparos, dias = avaliar_vencimento_proximo(date(2026, 12, 31), date(2026, 8, 16), [30, 15, 5])
        self.assertEqual(disparos, [])
        self.assertGreater(dias, 30)

    def test_operacao_ja_vencida_nao_dispara(self):
        disparos, dias = avaliar_vencimento_proximo(date(2026, 1, 1), date(2026, 8, 16), [30, 15, 5])
        self.assertEqual(disparos, [])
        self.assertLess(dias, 0)


class TestEventoBarreira(unittest.TestCase):
    def test_mudanca_dispara(self):
        resultado = avaliar_evento_barreira("nao_observada", "tocada", [])
        self.assertEqual(resultado, ("evento_barreira_tocada", "Mudança de status de barreira: 'nao_observada' -> 'tocada'"))

    def test_sem_mudanca_nao_dispara(self):
        self.assertIsNone(avaliar_evento_barreira("tocada", "tocada", []))

    def test_primeira_aparicao_nao_dispara(self):
        self.assertIsNone(avaliar_evento_barreira(None, "tocada", []))

    def test_status_nao_relevante_nao_dispara(self):
        self.assertIsNone(avaliar_evento_barreira("nao_observada", "proxima", ["tocada"]))

    def test_status_relevante_dispara(self):
        resultado = avaliar_evento_barreira("proxima", "tocada", ["tocada"])
        self.assertIsNotNone(resultado)


if __name__ == "__main__":
    unittest.main()
