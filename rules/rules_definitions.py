"""Funções puras que avaliam cada regra de negócio. Sem acesso a banco de
dados aqui — só datas e valores de entrada, para serem 100% testáveis
isoladamente (ver tests/test_rules.py)."""
from datetime import date


def meses_decorridos(data_fechamento: date, hoje: date) -> int:
    meses = (hoje.year - data_fechamento.year) * 12 + (hoje.month - data_fechamento.month)
    if hoje.day < data_fechamento.day:
        meses -= 1
    return max(meses, 0)


def dias_decorridos(data: date, hoje: date) -> int:
    return max((hoje - data).days, 0)


def avaliar_tempo_decorrido(data_fechamento: date, hoje: date, meses_config: list[int]) -> list[tuple[str, str]]:
    """Retorna lista de (regra_disparada, motivo) para cada limiar de meses
    já atingido desde o fechamento."""
    decorridos = meses_decorridos(data_fechamento, hoje)
    disparos = []
    for m in sorted(set(meses_config)):
        if decorridos >= m:
            regra = f"tempo_decorrido_{m}m"
            motivo = f"{m} mes(es) desde o fechamento (decorridos: {decorridos} mes(es))"
            disparos.append((regra, motivo))
    return disparos


def avaliar_vencimento_proximo(data_vencimento: date, hoje: date,
                                dias_config: list[int]) -> tuple[list[tuple[str, str]], int]:
    """Retorna (lista de (regra_disparada, motivo), dias_restantes).
    Não dispara para operações já vencidas (dias_restantes < 0)."""
    dias_restantes = (data_vencimento - hoje).days
    disparos = []
    if dias_restantes < 0:
        return disparos, dias_restantes
    for d in sorted(set(dias_config)):
        if dias_restantes <= d:
            regra = f"vencimento_{d}d"
            motivo = f"Vencimento em {dias_restantes} dia(s) (limite configurado: {d} dias)"
            disparos.append((regra, motivo))
    return disparos, dias_restantes


def avaliar_evento_barreira(status_anterior: str | None, status_atual: str | None,
                             status_relevantes: list[str]) -> tuple[str, str] | None:
    """Retorna (regra_disparada, motivo) se houve mudança de status de
    barreira relevante entre a importação anterior e a atual, senão None."""
    if not status_atual:
        return None
    if status_anterior is None:
        # primeira vez que a operação aparece no sistema: não é uma "mudança"
        return None
    if status_anterior == status_atual:
        return None
    if status_relevantes and status_atual not in status_relevantes:
        return None
    regra = f"evento_barreira_{status_atual}"
    motivo = f"Mudança de status de barreira: '{status_anterior}' -> '{status_atual}'"
    return regra, motivo
