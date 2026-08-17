"""Consultas e escritas usadas pela CLI do Jarvis. Centralizado aqui para
manter cli/main.py focado em parsing de argumentos e interação com o
usuário.

Nada neste módulo é uma "ação de negócio real": tudo aqui só lê/atualiza o
espelho local (clientes, operacoes, follow_ups, notas_pessoais). O CRM
oficial da corretora nunca é tocado por este projeto.
"""
from datetime import date, datetime

from rules.rules_definitions import dias_decorridos


def contar_pendentes(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM follow_ups WHERE status_revisao = 'pendente'").fetchone()["n"]


def listar_pendentes(conn):
    return conn.execute(
        """SELECT f.*, o.tipo_estrutura, o.ativo_objeto, o.data_vencimento, o.operacao_ref,
                  c.nome AS cliente_nome, c.codigo AS cliente_codigo
           FROM follow_ups f
           JOIN operacoes o ON o.id = f.operacao_id
           JOIN clientes c ON c.id = o.cliente_id
           WHERE f.status_revisao = 'pendente'
           ORDER BY o.data_vencimento ASC, f.data_gerado ASC"""
    ).fetchall()


def get_follow_up(conn, follow_up_id: int):
    return conn.execute(
        """SELECT f.*, o.tipo_estrutura, o.ativo_objeto, o.data_vencimento, o.operacao_ref,
                  c.nome AS cliente_nome, c.codigo AS cliente_codigo
           FROM follow_ups f
           JOIN operacoes o ON o.id = f.operacao_id
           JOIN clientes c ON c.id = o.cliente_id
           WHERE f.id = ?""",
        (follow_up_id,),
    ).fetchone()


def aprovar_follow_up(conn, follow_up_id: int, mensagem_final: str):
    conn.execute(
        "UPDATE follow_ups SET status_revisao = 'revisado', mensagem_final = ?, data_revisao = datetime('now') "
        "WHERE id = ?",
        (mensagem_final, follow_up_id),
    )
    conn.commit()


def descartar_follow_up(conn, follow_up_id: int):
    conn.execute(
        "UPDATE follow_ups SET status_revisao = 'descartado', data_revisao = datetime('now') WHERE id = ?",
        (follow_up_id,),
    )
    conn.commit()


def listar_revisados_para_exportar(conn):
    return conn.execute(
        """SELECT f.*, o.tipo_estrutura, o.ativo_objeto, o.data_vencimento, o.operacao_ref,
                  c.nome AS cliente_nome, c.codigo AS cliente_codigo
           FROM follow_ups f
           JOIN operacoes o ON o.id = f.operacao_id
           JOIN clientes c ON c.id = o.cliente_id
           WHERE f.status_revisao = 'revisado'
           ORDER BY o.data_vencimento ASC"""
    ).fetchall()


def marcar_exportados(conn, follow_up_ids: list[int]):
    conn.executemany(
        "UPDATE follow_ups SET status_revisao = 'exportado', data_revisao = datetime('now') WHERE id = ?",
        [(fid,) for fid in follow_up_ids],
    )
    conn.commit()


def listar_vencimentos_proximos(conn, dias_janela: int, hoje: date):
    limite = hoje.toordinal() + dias_janela
    cur = conn.execute(
        """SELECT o.*, c.nome AS cliente_nome, c.codigo AS cliente_codigo
           FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
           WHERE o.status = 'ativa'"""
    )
    resultado = []
    for row in cur.fetchall():
        data_vencimento = date.fromisoformat(row["data_vencimento"])
        dias_restantes = (data_vencimento - hoje).days
        if 0 <= dias_restantes <= dias_janela:
            resultado.append((row, dias_restantes))
    resultado.sort(key=lambda par: par[1])
    return resultado


def listar_barreiras_tocadas(conn, valores_tocada: list[str]):
    if not valores_tocada:
        return []
    placeholders = ",".join("?" for _ in valores_tocada)
    return conn.execute(
        f"""SELECT o.*, c.nome AS cliente_nome, c.codigo AS cliente_codigo
            FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
            WHERE o.status = 'ativa' AND o.status_barreira IN ({placeholders})""",
        valores_tocada,
    ).fetchall()


def listar_clientes_sem_contato(conn, dias_limite: int, hoje: date):
    """Proxy interno: para cada cliente com operação ativa, olha a
    data_fechamento mais recente entre as ativas. Se já se passaram mais de
    `dias_limite` dias, o cliente entra na lista. NÃO é o contato oficial
    registrado no CRM da corretora — é só um sinal de atenção do Jarvis."""
    cur = conn.execute(
        """SELECT c.nome AS cliente_nome, c.codigo AS cliente_codigo, MAX(o.data_fechamento) AS ultimo_fechamento
           FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
           WHERE o.status = 'ativa'
           GROUP BY c.id"""
    )
    resultado = []
    for row in cur.fetchall():
        ultimo_fechamento = date.fromisoformat(row["ultimo_fechamento"])
        dias = dias_decorridos(ultimo_fechamento, hoje)
        if dias > dias_limite:
            resultado.append({
                "cliente_nome": row["cliente_nome"], "cliente_codigo": row["cliente_codigo"],
                "dias_desde_ultimo_fechamento": dias,
            })
    resultado.sort(key=lambda r: -r["dias_desde_ultimo_fechamento"])
    return resultado


def get_cliente_por_codigo(conn, codigo: str):
    return conn.execute("SELECT * FROM clientes WHERE codigo = ?", (codigo,)).fetchone()


def briefing_cliente(conn, codigo: str) -> dict | None:
    cliente = get_cliente_por_codigo(conn, codigo)
    if cliente is None:
        return None

    operacoes_ativas = conn.execute(
        "SELECT * FROM operacoes WHERE cliente_id = ? AND status = 'ativa' ORDER BY data_vencimento ASC",
        (cliente["id"],),
    ).fetchall()

    follow_ups_pendentes = conn.execute(
        """SELECT f.* FROM follow_ups f JOIN operacoes o ON o.id = f.operacao_id
           WHERE o.cliente_id = ? AND f.status_revisao = 'pendente'
           ORDER BY f.data_gerado DESC""",
        (cliente["id"],),
    ).fetchall()

    notas = conn.execute(
        "SELECT * FROM notas_pessoais WHERE cliente_id = ? ORDER BY data_criacao DESC",
        (cliente["id"],),
    ).fetchall()

    return {
        "cliente": cliente,
        "operacoes_ativas": operacoes_ativas,
        "follow_ups_pendentes": follow_ups_pendentes,
        "notas": notas,
    }


def inserir_nota(conn, cliente_codigo: str, operacao_ref: str | None, texto: str) -> int:
    cliente = get_cliente_por_codigo(conn, cliente_codigo)
    if cliente is None:
        raise ValueError(f"Cliente com código '{cliente_codigo}' não encontrado.")

    operacao_id = None
    if operacao_ref:
        row = conn.execute(
            "SELECT id FROM operacoes WHERE cliente_id = ? AND operacao_ref = ?",
            (cliente["id"], operacao_ref),
        ).fetchone()
        if row is None:
            raise ValueError(f"Operação '{operacao_ref}' não encontrada para o cliente '{cliente_codigo}'.")
        operacao_id = row["id"]

    cur = conn.execute(
        "INSERT INTO notas_pessoais (cliente_id, operacao_id, texto) VALUES (?, ?, ?)",
        (cliente["id"], operacao_id, texto),
    )
    conn.commit()
    return cur.lastrowid
