"""Orquestração da importação diária: lê arquivo -> valida linhas -> upsert em
clientes/operacoes (com fonte_extracao/data_extracao) -> marca como
encerradas as operações que saíram do arquivo -> monta o relatório do que
mudou desde a extração anterior -> grava log_importacoes -> dispara o motor
de regras.

Escopo: isto é sempre um espelho local de uma extração manual do CRM
oficial. Nada aqui altera nada no sistema oficial — é só leitura de arquivo
+ upsert no banco local do Jarvis.

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
        # Relatório "o que mudou desde a extração anterior" (auditoria + `jarvis importar`)
        self.diff_novas: list[dict] = []
        self.diff_encerradas: list[dict] = []
        self.diff_mudancas_barreira: list[dict] = []

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


def _upsert_operacao(conn, cliente_id: int, registro: dict, fonte_extracao: str,
                      data_extracao: str) -> tuple[int, bool, str | None]:
    """Retorna (operacao_id, é_nova, status_barreira_anterior_se_mudou)."""
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
                parametros_json, status, fonte_extracao, data_extracao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'ativa', ?, ?)""",
            (
                registro["operacao_id"], cliente_id, registro["tipo_estrutura"], registro["ativo_objeto"],
                registro["data_fechamento"].isoformat(), registro["data_vencimento"].isoformat(),
                registro.get("strike_1"), registro.get("strike_2"), registro.get("barreira"),
                registro.get("status_barreira"), registro.get("valor_notional"),
                parametros_json, fonte_extracao, data_extracao,
            ),
        )
        return cur.lastrowid, True, None

    status_anterior = row["status_barreira"]
    status_novo = registro.get("status_barreira")
    conn.execute(
        """UPDATE operacoes SET
            tipo_estrutura = ?, ativo_objeto = ?, data_fechamento = ?, data_vencimento = ?,
            strike_1 = ?, strike_2 = ?, barreira = ?,
            status_barreira_anterior = ?, status_barreira = ?,
            valor_notional = ?, parametros_json = ?, status = 'ativa',
            fonte_extracao = ?, data_extracao = ?,
            data_ultima_atualizacao = datetime('now')
        WHERE id = ?""",
        (
            registro["tipo_estrutura"], registro["ativo_objeto"],
            registro["data_fechamento"].isoformat(), registro["data_vencimento"].isoformat(),
            registro.get("strike_1"), registro.get("strike_2"), registro.get("barreira"),
            status_anterior, status_novo,
            registro.get("valor_notional"), parametros_json,
            fonte_extracao, data_extracao, row["id"],
        ),
    )
    mudou = status_anterior != status_novo and status_anterior is not None
    return row["id"], False, (status_anterior if mudou else None)


def _marcar_encerradas(conn, refs_vistas: set[tuple[str, str]]) -> list[dict]:
    """Marca como 'encerrada' toda operação atualmente 'ativa' cujo par
    (codigo_cliente, operacao_ref) não apareceu no arquivo importado agora.
    Retorna a lista de operações encerradas, para o relatório de diff."""
    cur = conn.execute(
        """SELECT o.id, c.nome AS cliente_nome, c.codigo AS cliente_codigo,
                  o.operacao_ref, o.tipo_estrutura, o.ativo_objeto
           FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
           WHERE o.status = 'ativa'"""
    )
    encerradas = []
    for row in cur.fetchall():
        chave = (row["cliente_codigo"], row["operacao_ref"])
        if chave not in refs_vistas:
            conn.execute(
                "UPDATE operacoes SET status = 'encerrada', data_ultima_atualizacao = datetime('now') "
                "WHERE id = ?",
                (row["id"],),
            )
            encerradas.append({
                "cliente": row["cliente_nome"], "cliente_codigo": row["cliente_codigo"],
                "operacao_ref": row["operacao_ref"], "tipo_estrutura": row["tipo_estrutura"],
                "ativo_objeto": row["ativo_objeto"],
            })
    return encerradas


def executar_importacao(conn, caminho_arquivo, mapeamento: dict, rules_config: dict,
                         hoje: date | None = None) -> ResultadoImportacao:
    hoje = hoje or date.today()
    caminho_arquivo = Path(caminho_arquivo)
    resultado = ResultadoImportacao(str(caminho_arquivo.name))
    data_extracao = datetime.now().isoformat(timespec="seconds")

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
            operacao_id, era_nova, status_barreira_mudou_de = _upsert_operacao(
                conn, cliente_id, registro, resultado.arquivo, data_extracao
            )
            if era_nova:
                resultado.novas += 1
                resultado.diff_novas.append({
                    "cliente": registro["nome"], "cliente_codigo": registro["cliente_id"],
                    "operacao_ref": registro["operacao_id"], "tipo_estrutura": registro["tipo_estrutura"],
                    "ativo_objeto": registro["ativo_objeto"],
                })
            else:
                resultado.atualizadas += 1
                if status_barreira_mudou_de is not None:
                    resultado.diff_mudancas_barreira.append({
                        "cliente": registro["nome"], "cliente_codigo": registro["cliente_id"],
                        "operacao_ref": registro["operacao_id"],
                        "status_anterior": status_barreira_mudou_de,
                        "status_atual": registro.get("status_barreira"),
                    })

            refs_vistas.add((registro["cliente_id"], registro["operacao_id"]))

        resultado.diff_encerradas = _marcar_encerradas(conn, refs_vistas)
        resultado.encerradas = len(resultado.diff_encerradas)

        detalhes = {
            "erros": resultado.erros,
            "avisos": resultado.avisos,
            "diff": {
                "novas": resultado.diff_novas,
                "encerradas": resultado.diff_encerradas,
                "mudancas_barreira": resultado.diff_mudancas_barreira,
            },
        }
        conn.execute(
            """INSERT INTO log_importacoes
               (arquivo, linhas_processadas, novas, atualizadas, encerradas, erros, detalhes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                resultado.arquivo, resultado.linhas_processadas, resultado.novas,
                resultado.atualizadas, resultado.encerradas, len(resultado.erros),
                json.dumps(detalhes, ensure_ascii=False),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Motor de regras roda após a importação estar consolidada (fora da transação
    # de importação, com sua própria transação — ver rules/engine.py). Só prepara
    # RASCUNHOS de follow-up; nenhuma ação de negócio real acontece aqui.
    resultado.follow_ups_gerados = processar_regras(conn, rules_config, hoje=hoje)

    return resultado
