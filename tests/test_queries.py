import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import queries  # noqa: E402
from db.database import get_connection, init_db  # noqa: E402


class TestQueries(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "teste.db")
        init_db(self.db_path)
        self.conn = get_connection(self.db_path)
        self.hoje = date(2026, 8, 16)
        self._seed()

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _seed(self):
        c = self.conn
        c.execute("INSERT INTO clientes (codigo, nome, perfil_suitability) VALUES ('C1', 'Fulano', 'agressivo')")
        c.execute("INSERT INTO clientes (codigo, nome, perfil_suitability) VALUES ('C2', 'Beltrano', 'moderado')")
        cliente1 = c.execute("SELECT id FROM clientes WHERE codigo='C1'").fetchone()["id"]
        cliente2 = c.execute("SELECT id FROM clientes WHERE codigo='C2'").fetchone()["id"]

        # C1: operação que vence em 10 dias, barreira tocada, fechada há 60 dias (sem contato > 30d)
        c.execute(
            """INSERT INTO operacoes (operacao_ref, cliente_id, tipo_estrutura, ativo_objeto,
               data_fechamento, data_vencimento, status_barreira, status, fonte_extracao, data_extracao)
               VALUES ('OP1', ?, 'Autocall', 'PETR4', '2026-06-17', '2026-08-26', 'tocada', 'ativa', 'x.csv', '2026-08-16T00:00:00')""",
            (cliente1,),
        )
        # C2: operação recém fechada (5 dias atrás), sem barreira tocada, vence em 200 dias
        c.execute(
            """INSERT INTO operacoes (operacao_ref, cliente_id, tipo_estrutura, ativo_objeto,
               data_fechamento, data_vencimento, status_barreira, status, fonte_extracao, data_extracao)
               VALUES ('OP2', ?, 'Dual Currency', 'USDBRL', '2026-08-11', '2027-03-04', 'nao_observada', 'ativa', 'x.csv', '2026-08-16T00:00:00')""",
            (cliente2,),
        )
        op1_id = c.execute("SELECT id FROM operacoes WHERE operacao_ref='OP1'").fetchone()["id"]
        c.execute(
            """INSERT INTO follow_ups (operacao_id, regra_disparada, motivo_disparo, mensagem_gerada, mensagem_final, status_revisao)
               VALUES (?, 'vencimento_15d', 'motivo teste', 'mensagem original', 'mensagem original', 'pendente')""",
            (op1_id,),
        )
        c.commit()
        self.op1_id = op1_id
        self.cliente1 = cliente1

    def test_contar_e_listar_pendentes(self):
        self.assertEqual(queries.contar_pendentes(self.conn), 1)
        pendentes = queries.listar_pendentes(self.conn)
        self.assertEqual(len(pendentes), 1)
        self.assertEqual(pendentes[0]["cliente_codigo"], "C1")

    def test_aprovar_follow_up_grava_mensagem_final_e_muda_status(self):
        follow_up_id = queries.listar_pendentes(self.conn)[0]["id"]
        queries.aprovar_follow_up(self.conn, follow_up_id, "mensagem editada pelo usuário")
        row = queries.get_follow_up(self.conn, follow_up_id)
        self.assertEqual(row["status_revisao"], "revisado")
        self.assertEqual(row["mensagem_final"], "mensagem editada pelo usuário")
        self.assertEqual(row["mensagem_gerada"], "mensagem original")  # original preservado
        self.assertEqual(queries.contar_pendentes(self.conn), 0)

    def test_descartar_follow_up(self):
        follow_up_id = queries.listar_pendentes(self.conn)[0]["id"]
        queries.descartar_follow_up(self.conn, follow_up_id)
        row = queries.get_follow_up(self.conn, follow_up_id)
        self.assertEqual(row["status_revisao"], "descartado")

    def test_exportar_marca_como_exportado(self):
        follow_up_id = queries.listar_pendentes(self.conn)[0]["id"]
        queries.aprovar_follow_up(self.conn, follow_up_id, "pronto para exportar")
        revisados = queries.listar_revisados_para_exportar(self.conn)
        self.assertEqual(len(revisados), 1)
        queries.marcar_exportados(self.conn, [r["id"] for r in revisados])
        self.assertEqual(queries.listar_revisados_para_exportar(self.conn), [])
        row = queries.get_follow_up(self.conn, follow_up_id)
        self.assertEqual(row["status_revisao"], "exportado")

    def test_listar_vencimentos_proximos(self):
        resultado = queries.listar_vencimentos_proximos(self.conn, dias_janela=15, hoje=self.hoje)
        self.assertEqual(len(resultado), 1)
        op, dias = resultado[0]
        self.assertEqual(op["operacao_ref"], "OP1")
        self.assertEqual(dias, 10)

    def test_listar_barreiras_tocadas(self):
        resultado = queries.listar_barreiras_tocadas(self.conn, ["tocada", "rompida"])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["operacao_ref"], "OP1")

    def test_listar_clientes_sem_contato(self):
        resultado = queries.listar_clientes_sem_contato(self.conn, dias_limite=30, hoje=self.hoje)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["cliente_codigo"], "C1")
        self.assertEqual(resultado[0]["dias_desde_ultimo_fechamento"], 60)

    def test_briefing_cliente(self):
        info = queries.briefing_cliente(self.conn, "C1")
        self.assertIsNotNone(info)
        self.assertEqual(info["cliente"]["nome"], "Fulano")
        self.assertEqual(len(info["operacoes_ativas"]), 1)
        self.assertEqual(len(info["follow_ups_pendentes"]), 1)
        self.assertEqual(info["notas"], [])

    def test_briefing_cliente_inexistente(self):
        self.assertIsNone(queries.briefing_cliente(self.conn, "NAO_EXISTE"))

    def test_inserir_nota_sobre_cliente(self):
        nota_id = queries.inserir_nota(self.conn, "C1", None, "Ligou hoje.")
        self.assertGreater(nota_id, 0)
        info = queries.briefing_cliente(self.conn, "C1")
        self.assertEqual(len(info["notas"]), 1)
        self.assertEqual(info["notas"][0]["texto"], "Ligou hoje.")
        self.assertIsNone(info["notas"][0]["operacao_id"])

    def test_inserir_nota_sobre_operacao(self):
        queries.inserir_nota(self.conn, "C1", "OP1", "Falou sobre a barreira.")
        info = queries.briefing_cliente(self.conn, "C1")
        self.assertEqual(info["notas"][0]["operacao_id"], self.op1_id)

    def test_inserir_nota_cliente_inexistente_levanta_erro(self):
        with self.assertRaises(ValueError):
            queries.inserir_nota(self.conn, "NAO_EXISTE", None, "texto")

    def test_inserir_nota_operacao_inexistente_levanta_erro(self):
        with self.assertRaises(ValueError):
            queries.inserir_nota(self.conn, "C1", "OP_NAO_EXISTE", "texto")


if __name__ == "__main__":
    unittest.main()
