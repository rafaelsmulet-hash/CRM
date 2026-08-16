"""Orquestração da importação diária: lê arquivo -> valida linhas -> upsert em
clientes/operacoes -> marca como encerradas as operações que saíram do
arquivo -> grava log_importacoes -> dispara o motor de regras.

Tudo roda em uma única transação SQLite por importação: se algo inesperado
falhar no meio do processo, nada fica gravado pela metade (rollback).
"""
import json
from datetime import date, datetime
from pathlib import Path

from importer.file_reader import ArquivoInvalidoError, ler_arquivo
from importer.validators import (
    LinhaInvalidaError, extrair_linha, validar_colunas_presentes,
)
from rules.engine import processar_regras


class ResultadoImportacao:
    def __init__(self, arquivo: str):
        self.arquivo = arquivo
        self.linhas_processadas = 0
        self.novas = 0
        self.atualizadas = 0
        self.encerradas = 0
        self.erros: list[dict] = []
        self.avisos: list[dict] = []
        self.follow_ups_gerados = 0

    def as_dict(self):
        return {
            "arquivo": self.arquivo,
            "linhas_processadas": self.linhas_processadas,
            "novas": self.novas,
            "atualizadas": self.atualizadas,
            "encerradas": self.encerradas,
            "erros": len(self.erros),
            "avisos": len(self.avisos),
            "follow_ups_gerados": self.follow_ups_gerados,
        }


def _upsert_cliente(conn, codigo: str, nome: str, perfil_suitability):
    cur = conn.execute("SELECT id, nome, perfil_suitability FROM clientes WHERE codigo = ?", (codigo,))
    row = cur.fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO clientes (codigo, nome, perfil_suitability) VALUES (?, ?, ?)",
            (codigo, nome, perfil_suitability),
        )
        return cur.lastrowid
    if row["nome"] != nome or row["perfil_suitability"] != perfil_suitability:
        conn.execute(
            "UPDATE clientes SET nome = ?, perfil_suitability = ?, data_ultima_atualizacao = datetime('now') "
            "WHERE id = ?",
            (nome, perfil_suitability, row["id"]),
        )
    return row["id"]


def _upsert_operacao(conn, cliente_id: int, registro: dict) -> tuple[int, bool]:
    """Retorna (operacao_id, é_nova)."""
    cur = conn.execute(
        "SELECT id, status_barreira FROM operacoes WHERE cliente_id = ? AND operacao_ref = ?",
        (cliente_id, registro["operacao_id"]),
    )
    row = cur.fetchone()
    parametros_json = json.dumps(registro.get("_linha_bruta", {}), ensure_ascii=False)

    if row is None:
        cur = conn.execute(
            """INSERT INTO operacoes (
                operacao_ref, cliente_id, tipo_estrutura, ativo_objeto,
                data_fechamento, data_vencimento, strike_1, strike_2, barreira,
                status_barreira, status_barreira_anterior, valor_notional,
                parametros_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'ativa')""",
            (
                registro["operacao_id"], cliente_id, registro["tipo_estrutura"], registro["ativo_objeto"],
                registro["data_fechamento"].isoformat(), registro["data_vencimento"].isoformat(),
                registro.get("strike_1"), registro.get("strike_2"), registro.get("barreira"),
                registro.get("status_barreira"), registro.get("valor_notional"),
                parametros_json,
            ),
        )
        return cur.lastrowid, True

    status_anterior = row["status_barreira"]
    conn.execute(
        """UPDATE operacoes SET
            tipo_estrutura = ?, ativo_objeto = ?, data_fechamento = ?, data_vencimento = ?,
            strike_1 = ?, strike_2 = ?, barreira = ?,
            status_barreira_anterior = ?, status_barreira = ?,
            valor_notional = ?, parametros_json = ?, status = 'ativa',
            data_ultima_atualizacao = datetime('now')
        WHERE id = ?""",
        (
            registro["tipo_estrutura"], registro["ativo_objeto"],
            registro["data_fechamento"].isoformat(), registro["data_vencimento"].isoformat(),
            registro.get("strike_1"), registro.get("strike_2"), registro.get("barreira"),
            status_anterior, registro.get("status_barreira"),
            registro.get("valor_notional"), parametros_json, row["id"],
        ),
    )
    return row["id"], False


def _marcar_encerradas(conn, refs_vistas: set[tuple[str, str]]) -> int:
    """Marca como 'encerrada' toda operação atualmente 'ativa' cujo par
    (codigo_cliente, operacao_ref) não apareceu no arquivo importado agora."""
    cur = conn.execute(
        """SELECT o.id, c.codigo AS cliente_codigo, o.operacao_ref
           FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
           WHERE o.status = 'ativa'"""
    )
    encerradas = 0
    for row in cur.fetchall():
        chave = (row["cliente_codigo"], row["operacao_ref"])
        if chave not in refs_vistas:
            conn.execute(
                "UPDATE operacoes SET status = 'encerrada', data_ultima_atualizacao = datetime('now') "
                "WHERE id = ?",
                (row["id"],),
            )
            encerradas += 1
    return encerradas


def executar_importacao(conn, caminho_arquivo, mapeamento: dict, rules_config: dict,
                         hoje: date | None = None) -> ResultadoImportacao:
    hoje = hoje or date.today()
    caminho_arquivo = Path(caminho_arquivo)
    resultado = ResultadoImportacao(str(caminho_arquivo.name))

    colunas_arquivo, linhas_arquivo = ler_arquivo(caminho_arquivo)  # levanta ArquivoInvalidoError se estrutural

    colunas_mapeadas = mapeamento.get("colunas", {})
    faltando = validar_colunas_presentes(colunas_arquivo, colunas_mapeadas)
    if faltando:
        raise ArquivoInvalidoError(
            "Colunas obrigatórias ausentes no arquivo: " + "; ".join(faltando)
        )

    formato_data = mapeamento.get("formato_data", "%d/%m/%Y")
    separador_decimal = mapeamento.get("separador_decimal", ",")

    refs_vistas: set[tuple[str, str]] = set()

    conn.execute("BEGIN")
    try:
        for idx, linha in enumerate(linhas_arquivo, start=2):  # linha 2 = primeira linha de dados (após cabeçalho)
            resultado.linhas_processadas += 1
            try:
                registro, avisos = extrair_linha(linha, colunas_mapeadas, formato_data, separador_decimal)
            except LinhaInvalidaError as e:
                resultado.erros.append({"linha": idx, "motivo": e.motivo})
                continue

            for aviso in avisos:
                resultado.avisos.append({"linha": idx, "motivo": aviso})

            registro["_linha_bruta"] = linha
            cliente_id = _upsert_cliente(
                conn, registro["cliente_id"], registro["nome"], registro.get("perfil_suitability")
            )
            _, era_nova = _upsert_operacao(conn, cliente_id, registro)
            if era_nova:
                resultado.novas += 1
            else:
                resultado.atualizadas += 1

            refs_vistas.add((registro["cliente_id"], registro["operacao_id"]))

        resultado.encerradas = _marcar_encerradas(conn, refs_vistas)

        conn.execute(
            """INSERT INTO log_importacoes
               (arquivo, linhas_processadas, novas, atualizadas, encerradas, erros, detalhes_erros)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                resultado.arquivo, resultado.linhas_processadas, resultado.novas,
                resultado.atualizadas, resultado.encerradas, len(resultado.erros),
                json.dumps({"erros": resultado.erros, "avisos": resultado.avisos}, ensure_ascii=False),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Motor de regras roda após a importação estar consolidada (fora da transação
    # de importação, com sua própria transação — ver rules/engine.py).
    resultado.follow_ups_gerados = processar_regras(conn, rules_config, hoje=hoje)

    return resultado
