import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_connection, init_db  # noqa: E402
from importer.import_run import executar_importacao  # noqa: E402
from settings import carregar_column_mapping, carregar_rules_config  # noqa: E402

CAMPOS = [
    "cliente_id", "nome", "tipo_estrutura", "ativo_objeto", "data_fechamento",
    "data_vencimento", "operacao_id", "strike_1", "strike_2", "barreira",
    "status_barreira", "valor_notional", "perfil_suitability",
]


def escrever_csv(caminho: Path, linhas: list[dict]):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        for linha in linhas:
            writer.writerow(linha)


LINHA_C2_BASE = {
    "cliente_id": "C2", "nome": "Beltrano da Silva", "tipo_estrutura": "Dual Currency",
    "ativo_objeto": "USDBRL", "data_fechamento": "16/08/2026", "data_vencimento": "01/01/2027",
    "operacao_id": "OP2", "strike_1": "5", "strike_2": "6", "barreira": "",
    "status_barreira": "nao_observada", "valor_notional": "500000", "perfil_suitability": "moderado",
}


def linha_op1(status_barreira="tocada"):
    return {
        "cliente_id": "C1", "nome": "Fulano de Tal", "tipo_estrutura": "Autocall",
        "ativo_objeto": "PETR4", "data_fechamento": "16/07/2025", "data_vencimento": "19/08/2026",
        "operacao_id": "OP1", "strike_1": "30", "strike_2": "", "barreira": "25",
        "status_barreira": status_barreira, "valor_notional": "1000000", "perfil_suitability": "agressivo",
    }


class TestImportacaoERegras(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "teste.db")
        init_db(self.db_path)
        self.mapeamento = carregar_column_mapping()
        self.rules_config = carregar_rules_config()
        self.hoje = date(2026, 8, 16)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _importar(self, linhas, nome_arquivo="import.csv"):
        caminho = Path(self.tmpdir.name) / nome_arquivo
        escrever_csv(caminho, linhas)
        conn = get_connection(self.db_path)
        try:
            resultado = executar_importacao(conn, caminho, self.mapeamento, self.rules_config, hoje=self.hoje)
        finally:
            conn.close()
        return resultado

    def _follow_ups_operacao(self, operacao_ref):
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT f.* FROM follow_ups f JOIN operacoes o ON o.id = f.operacao_id
                   WHERE o.operacao_ref = ?""",
                (operacao_ref,),
            ).fetchall()
        finally:
            conn.close()
        return rows

    def _status_operacao(self, operacao_ref):
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM operacoes WHERE operacao_ref = ?", (operacao_ref,)
            ).fetchone()
        finally:
            conn.close()
        return row["status"] if row else None

    def test_fluxo_completo(self):
        # --- Importação 1: cria as duas operações. OP1 dispara tempo (1,3,6,12m) e vencimento (30,15,5d). ---
        resultado1 = self._importar([linha_op1("tocada"), dict(LINHA_C2_BASE)], "imp1.csv")
        self.assertEqual(resultado1.novas, 2)
        self.assertEqual(resultado1.atualizadas, 0)
        self.assertEqual(resultado1.erros, [])
        self.assertEqual(resultado1.follow_ups_gerados, 7)  # 4 tempo + 3 vencimento; sem evento (1ª aparição)

        fus_op1 = self._follow_ups_operacao("OP1")
        self.assertEqual(len(fus_op1), 7)
        regras = {row["regra_disparada"] for row in fus_op1}
        self.assertEqual(
            regras,
            {"tempo_decorrido_1m", "tempo_decorrido_3m", "tempo_decorrido_6m", "tempo_decorrido_12m",
             "vencimento_30d", "vencimento_15d", "vencimento_5d"},
        )
        self.assertEqual(len(self._follow_ups_operacao("OP2")), 0)

        # --- Importação 2: só muda status_barreira de OP1. Regras de tempo/vencimento já
        # dispararam e não devem duplicar; só o evento de barreira deve gerar 1 novo follow-up. ---
        resultado2 = self._importar([linha_op1("rompida"), dict(LINHA_C2_BASE)], "imp2.csv")
        self.assertEqual(resultado2.novas, 0)
        self.assertEqual(resultado2.atualizadas, 2)
        self.assertEqual(resultado2.follow_ups_gerados, 1)

        fus_op1_depois = self._follow_ups_operacao("OP1")
        self.assertEqual(len(fus_op1_depois), 8)
        regra_evento = [r for r in fus_op1_depois if r["regra_disparada"].startswith("evento_barreira")]
        self.assertEqual(len(regra_evento), 1)
        self.assertEqual(regra_evento[0]["regra_disparada"], "evento_barreira_rompida")

        # --- Importação 3: OP1 sai do arquivo -> deve ser marcada como encerrada e parar de gerar follow-ups. ---
        resultado3 = self._importar([dict(LINHA_C2_BASE)], "imp3.csv")
        self.assertEqual(resultado3.encerradas, 1)
        self.assertEqual(self._status_operacao("OP1"), "encerrada")
        self.assertEqual(resultado3.follow_ups_gerados, 0)
        self.assertEqual(len(self._follow_ups_operacao("OP1")), 8)  # não ganhou novos follow-ups

    def test_linha_invalida_nao_derruba_importacao_inteira(self):
        linha_invalida = dict(LINHA_C2_BASE, cliente_id="", operacao_id="OP_INVALIDA")
        resultado = self._importar([linha_op1(), linha_invalida], "imp_com_erro.csv")
        self.assertEqual(resultado.novas, 1)
        self.assertEqual(len(resultado.erros), 1)
        self.assertEqual(resultado.linhas_processadas, 2)


if __name__ == "__main__":
    unittest.main()
