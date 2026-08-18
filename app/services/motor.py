"""Avaliador de regras — roda logo após o import do Orbit, no mesmo job.

Orquestra as funções puras de `regras.py` sobre os dados reais do banco:
barreira (distância/atingimento), fixing próximo, vencimento próximo. Gera
eventos (linha do tempo) e alertas (com dedupe), igual ao motor do Jarvis
CLI — só que agora alimentado pelo import do Orbit em vez de CSV manual.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import carregar_rules_config
from app.models import (
    Alerta,
    Barreira,
    Estrutura,
    Evento,
    Fixing,
    LogExecucaoMotor,
    PrecoMercado,
    Severidade,
    StatusEstrutura,
    StatusFixing,
)
from app.services.regras import (
    avaliar_barreira,
    dias_ate,
    fixing_deve_alertar,
    vencimento_deve_alertar,
)


def _criar_alerta_se_novo(
    db: Session, *, chave_dedupe: str, estrutura_id: int, evento_id: int | None, tipo: str,
    severidade: Severidade, mensagem: str,
) -> bool:
    """Mesma chave nunca gera dois alertas — evita spam ao rodar todo dia."""
    ja_existe = db.scalar(select(Alerta.id).where(Alerta.chave_dedupe == chave_dedupe))
    if ja_existe:
        return False
    db.add(
        Alerta(
            estrutura_id=estrutura_id,
            evento_id=evento_id,
            tipo=tipo,
            severidade=severidade,
            mensagem=mensagem,
            chave_dedupe=chave_dedupe,
        )
    )
    return True


def _avaliar_barreiras(db: Session, estrutura: Estrutura, hoje: datetime.date, limiar_proxima_pct: float) -> int:
    eventos_gerados = 0
    for barreira in estrutura.barreiras:
        ultimo_preco = db.scalar(
            select(PrecoMercado)
            .where(PrecoMercado.ticker == barreira.ativo_referencia)
            .order_by(PrecoMercado.data.desc())
            .limit(1)
        )
        if ultimo_preco is None:
            continue

        resultado = avaliar_barreira(
            preco_fechamento_anterior=float(ultimo_preco.preco),
            nivel=float(barreira.nivel),
            direcao=barreira.direcao,
            proxima_pct_limiar=limiar_proxima_pct,
        )

        if resultado.status_novo != barreira.status_atual:
            status_anterior = barreira.status_atual
            barreira.status_anterior = status_anterior
            barreira.status_atual = resultado.status_novo

            evento = Evento(
                estrutura_id=estrutura.id,
                tipo_evento="barreira",
                data_hora=datetime.datetime.now(datetime.timezone.utc),
                preco_referencia=ultimo_preco.preco,
                fonte=ultimo_preco.fonte,
                regra_utilizada=(
                    f"fechamento anterior vs. nível ({barreira.direcao}), "
                    f"limiar de proximidade {limiar_proxima_pct}%"
                ),
                status_anterior=status_anterior.value,
                status_novo=resultado.status_novo.value,
                detalhes={"distancia_pct": resultado.distancia_pct, "barreira_id": barreira.id},
            )
            db.add(evento)
            db.flush()
            eventos_gerados += 1

            if resultado.status_novo.value == "atingida":
                _criar_alerta_se_novo(
                    db,
                    chave_dedupe=f"barreira_atingida:{barreira.id}:{hoje.isoformat()}",
                    estrutura_id=estrutura.id,
                    evento_id=evento.id,
                    tipo="barreira_atingida",
                    severidade=Severidade.critico,
                    mensagem=(
                        f"{estrutura.operacao_ref} ({estrutura.cliente.nome}): barreira {barreira.tipo} "
                        f"atingida — {barreira.ativo_referencia} fechou em {ultimo_preco.preco}, "
                        f"nível {barreira.nivel}."
                    ),
                )
            elif resultado.status_novo.value == "proxima":
                _criar_alerta_se_novo(
                    db,
                    chave_dedupe=f"barreira_proxima:{barreira.id}:{hoje.isoformat()}",
                    estrutura_id=estrutura.id,
                    evento_id=evento.id,
                    tipo="barreira_proxima",
                    severidade=Severidade.atencao,
                    mensagem=(
                        f"{estrutura.operacao_ref} ({estrutura.cliente.nome}): barreira {barreira.tipo} "
                        f"a {resultado.distancia_pct:.2f}% de distância."
                    ),
                )
    return eventos_gerados


def _avaliar_fixings(db: Session, estrutura: Estrutura, hoje: datetime.date, limiares: list[int]) -> None:
    for fixing in estrutura.fixings:
        if fixing.status != StatusFixing.pendente:
            continue
        restantes = dias_ate(fixing.data_fixing, hoje)
        if fixing_deve_alertar(dias_restantes=restantes, limiares_dias_antes=limiares, status=fixing.status):
            _criar_alerta_se_novo(
                db,
                chave_dedupe=f"fixing_proximo:{fixing.id}:{restantes}",
                estrutura_id=estrutura.id,
                evento_id=None,
                tipo="fixing_proximo",
                severidade=Severidade.info if restantes > 1 else Severidade.atencao,
                mensagem=(
                    f"{estrutura.operacao_ref} ({estrutura.cliente.nome}): fixing de {fixing.tipo} "
                    f"em {restantes} dia(s) — {fixing.data_fixing}."
                ),
            )


def _avaliar_vencimento(db: Session, estrutura: Estrutura, hoje: datetime.date, limiares: list[int]) -> None:
    if not estrutura.data_vencimento:
        return
    restantes = dias_ate(estrutura.data_vencimento, hoje)
    if vencimento_deve_alertar(dias_restantes=restantes, limiares_dias_antes=limiares):
        _criar_alerta_se_novo(
            db,
            chave_dedupe=f"vencimento_proximo:{estrutura.id}:{restantes}",
            estrutura_id=estrutura.id,
            evento_id=None,
            tipo="vencimento_proximo",
            severidade=Severidade.info if restantes > 5 else Severidade.atencao,
            mensagem=(
                f"{estrutura.operacao_ref} ({estrutura.cliente.nome}): vencimento em {restantes} dia(s) "
                f"— {estrutura.data_vencimento}."
            ),
        )


def executar(db: Session, data_referencia: datetime.date | None = None) -> LogExecucaoMotor:
    """Avalia todas as estruturas ativas. Reexecutável para uma data específica."""
    hoje = data_referencia or datetime.date.today()
    inicio = datetime.datetime.now(datetime.timezone.utc)
    regras_cfg = carregar_rules_config()

    log = LogExecucaoMotor(data_execucao=hoje, inicio=inicio, erros=[])
    estruturas_processadas = 0
    eventos_gerados = 0

    estruturas = (
        db.scalars(
            select(Estrutura)
            .where(Estrutura.status == StatusEstrutura.ativa)
            .options(
                joinedload(Estrutura.cliente),
                joinedload(Estrutura.barreiras),
                joinedload(Estrutura.fixings),
            )
        )
        .unique()
        .all()
    )
    for estrutura in estruturas:
        try:
            eventos_gerados += _avaliar_barreiras(db, estrutura, hoje, regras_cfg["barreira_proxima_pct"])
            _avaliar_fixings(db, estrutura, hoje, regras_cfg["fixing_alertas_dias_antes"])
            _avaliar_vencimento(db, estrutura, hoje, regras_cfg["vencimento_alertas_dias_antes"])
            estruturas_processadas += 1
        except Exception as exc:  # noqa: BLE001 — uma estrutura com erro não pode travar as outras
            log.erros.append({"estrutura_id": estrutura.id, "motivo": str(exc)})

    log.fim = datetime.datetime.now(datetime.timezone.utc)
    log.estruturas_processadas = estruturas_processadas
    log.eventos_gerados = eventos_gerados
    db.add(log)
    db.flush()
    return log
