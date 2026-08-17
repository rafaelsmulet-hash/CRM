"""Motor de regras: roda após cada importação (ou sob demanda) sobre todas as
operações ativas, decide quais follow-ups devem ser gerados, evita
duplicidade e grava os registros em follow_ups usando mensagens geradas por
template (nunca texto livre / nunca geração por LLM)."""
from datetime import date

from rules.rules_definitions import (
    avaliar_evento_barreira, avaliar_tempo_decorrido, avaliar_vencimento_proximo,
)
from templates.message_generator import gerar_mensagem, carregar_templates


def _ja_disparada(conn, operacao_id: int, regra_disparada: str) -> bool:
    """Uma regra só dispara UMA VEZ por operação (independente do status de
    revisão do follow-up gerado). Isso evita spam ao re-rodar a importação
    diariamente enquanto a condição continuar verdadeira."""
    cur = conn.execute(
        "SELECT 1 FROM follow_ups WHERE operacao_id = ? AND regra_disparada = ? LIMIT 1",
        (operacao_id, regra_disparada),
    )
    return cur.fetchone() is not None


def _inserir_follow_up(conn, operacao_id: int, regra_disparada: str, motivo: str, mensagem: str):
    """mensagem_final começa idêntica a mensagem_gerada; `jarvis revisar` pode
    editar mensagem_final, mas mensagem_gerada nunca é alterada (preserva o
    rascunho original gerado por template, para auditoria)."""
    conn.execute(
        """INSERT INTO follow_ups
               (operacao_id, regra_disparada, motivo_disparo, mensagem_gerada, mensagem_final, status_revisao)
           VALUES (?, ?, ?, ?, ?, 'pendente')""",
        (operacao_id, regra_disparada, motivo, mensagem, mensagem),
    )


def processar_regras(conn, rules_config: dict, hoje: date | None = None) -> int:
    """Avalia as regras configuradas para todas as operações ativas e insere
    os follow-ups pendentes correspondentes. Retorna o total de follow-ups
    gerados nesta execução."""
    hoje = hoje or date.today()
    templates = carregar_templates()

    cfg_tempo = rules_config.get("regra_tempo_decorrido", {})
    cfg_vencimento = rules_config.get("regra_vencimento_proximo", {})
    cfg_evento = rules_config.get("regra_evento_barreira", {})

    cur = conn.execute(
        """SELECT o.*, c.nome AS cliente_nome, c.codigo AS cliente_codigo
           FROM operacoes o JOIN clientes c ON c.id = o.cliente_id
           WHERE o.status = 'ativa'"""
    )
    operacoes = cur.fetchall()

    gerados = 0
    conn.execute("BEGIN")
    try:
        for op in operacoes:
            data_fechamento = date.fromisoformat(op["data_fechamento"])
            data_vencimento = date.fromisoformat(op["data_vencimento"])

            candidatos: list[tuple[str, str, int | None]] = []

            if cfg_tempo.get("ativa", True):
                for regra, motivo in avaliar_tempo_decorrido(data_fechamento, hoje, cfg_tempo.get("meses", [])):
                    dias_restantes = (data_vencimento - hoje).days
                    candidatos.append((regra, motivo, dias_restantes))

            if cfg_vencimento.get("ativa", True):
                disparos, dias_restantes = avaliar_vencimento_proximo(
                    data_vencimento, hoje, cfg_vencimento.get("dias_antes", [])
                )
                for regra, motivo in disparos:
                    candidatos.append((regra, motivo, dias_restantes))

            if cfg_evento.get("ativa", True):
                disparo = avaliar_evento_barreira(
                    op["status_barreira_anterior"], op["status_barreira"],
                    cfg_evento.get("status_relevantes", []),
                )
                if disparo:
                    regra, motivo = disparo
                    dias_restantes = (data_vencimento - hoje).days
                    candidatos.append((regra, motivo, dias_restantes))

            for regra, motivo, dias_restantes in candidatos:
                if _ja_disparada(conn, op["id"], regra):
                    continue
                mensagem = gerar_mensagem(dict(op), motivo, dias_restantes, templates=templates)
                _inserir_follow_up(conn, op["id"], regra, motivo, mensagem)
                gerados += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return gerados
