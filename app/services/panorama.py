"""Geração do rascunho de panorama mensal — mesmo padrão de template do Jarvis CLI.

Texto puro, sem YAML/JSON, editável por quem não programa. Um placeholder
digitado errado aparece como `[nome_errado?]` em vez de quebrar a geração —
fica visível já na revisão manual. Nenhum LLM gera este texto: é sempre
template + dados, para saída previsível e auditável.
"""
import datetime
import re
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Estrutura, Evento, Fixing, PrecoMercado, StatusFixing
from app.services.regras import calcular_distancia_pct

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def _carregar_template(tipo_estrutura: str) -> str:
    diretorio = Path(get_settings().diretorio_templates_panorama)
    caminho = diretorio / f"{_slug(tipo_estrutura)}.txt"
    if not caminho.exists():
        caminho = diretorio / "default.txt"
    return caminho.read_text(encoding="utf-8")


def _renderizar(template: str, dados: dict) -> str:
    def substituir(match: re.Match) -> str:
        chave = match.group(1)
        return str(dados[chave]) if chave in dados else f"[{chave}?]"

    return _PLACEHOLDER_RE.sub(substituir, template)


def montar_dados(db: Session, estrutura: Estrutura, competencia: str) -> dict:
    hoje = datetime.date.today()
    barreira = estrutura.barreiras[0] if estrutura.barreiras else None

    inicio_periodo = datetime.datetime.combine(
        hoje.replace(day=1), datetime.time.min, tzinfo=datetime.timezone.utc
    )
    eventos = db.scalars(
        select(Evento)
        .where(Evento.estrutura_id == estrutura.id, Evento.data_hora >= inicio_periodo)
        .order_by(Evento.data_hora)
    ).all()
    eventos_texto = (
        "\n".join(f"- {e.data_hora.strftime('%d/%m')}: {e.tipo_evento} ({e.status_novo or ''})" for e in eventos)
        or "- Nenhum evento relevante no período."
    )

    fixings = db.scalars(
        select(Fixing)
        .where(
            Fixing.estrutura_id == estrutura.id,
            Fixing.status == StatusFixing.pendente,
            Fixing.data_fixing >= hoje,
        )
        .order_by(Fixing.data_fixing)
        .limit(5)
    ).all()
    fixings_texto = (
        "\n".join(f"- {f.data_fixing.strftime('%d/%m/%Y')} ({f.tipo})" for f in fixings)
        or "- Nenhum fixing pendente no momento."
    )

    dias_restantes = (estrutura.data_vencimento - hoje).days if estrutura.data_vencimento else None

    distancia_texto = "sem barreira cadastrada"
    if barreira:
        ultimo_preco = db.scalar(
            select(PrecoMercado)
            .where(PrecoMercado.ticker == barreira.ativo_referencia)
            .order_by(PrecoMercado.data.desc())
            .limit(1)
        )
        if ultimo_preco:
            distancia = calcular_distancia_pct(float(ultimo_preco.preco), float(barreira.nivel))
            distancia_texto = f"{distancia:.2f}%"
        else:
            distancia_texto = "sem preço importado ainda"

    return {
        "cliente": estrutura.cliente.nome,
        "operacao_ref": estrutura.operacao_ref,
        "tipo_estrutura": estrutura.tipo_estrutura,
        "ativo_principal": estrutura.ativo_principal,
        "data_inicio": estrutura.data_inicio,
        "data_vencimento": estrutura.data_vencimento,
        "dias_restantes": dias_restantes if dias_restantes is not None else "—",
        "notional": estrutura.notional or "—",
        "competencia": competencia,
        "status_barreira": barreira.status_atual.value if barreira else "sem barreira cadastrada",
        "barreira_nivel": barreira.nivel if barreira else "—",
        "distancia_barreira_pct": distancia_texto,
        "eventos_recentes": eventos_texto,
        "proximos_fixings": fixings_texto,
    }


def gerar_texto(db: Session, estrutura: Estrutura, competencia: str) -> str:
    template = _carregar_template(estrutura.tipo_estrutura)
    dados = montar_dados(db, estrutura, competencia)
    return _renderizar(template, dados)
