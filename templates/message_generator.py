"""Geração de mensagens 100% por template parametrizado — sem LLM, local ou
externo. Saída determinística e auditável: a mesma operação + o mesmo motivo
sempre geram exatamente a mesma mensagem."""
from pathlib import Path
import unicodedata
import yaml

TEMPLATES_PATH = Path(__file__).parent / "templates.yaml"


class _ContextoComFallback(dict):
    """dict que, para chave ausente no .format_map(), devolve um marcador
    visível [chave?] em vez de levantar KeyError — assim um placeholder
    digitado errado no template aparece na mensagem gerada (fácil de pegar
    na revisão manual) em vez de quebrar a geração inteira."""

    def __missing__(self, key):
        return f"[{key}?]"


def _slugify(valor: str) -> str:
    valor = (valor or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", valor)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "_".join(sem_acento.split())


def carregar_templates() -> dict:
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        dados = yaml.safe_load(f) or {}
    if "default" not in dados:
        raise ValueError("templates.yaml precisa ter obrigatoriamente uma entrada 'default'.")
    return dados


def _ou_nd(valor):
    return valor if valor not in (None, "") else "N/D"


def gerar_mensagem(operacao: dict, motivo_disparo: str, dias_restantes, templates: dict = None) -> str:
    templates = templates or carregar_templates()
    slug = _slugify(operacao.get("tipo_estrutura", ""))
    template_str = templates.get(slug, templates["default"])

    contexto = _ContextoComFallback(
        cliente=operacao.get("cliente_nome") or operacao.get("nome"),
        nome=operacao.get("cliente_nome") or operacao.get("nome"),
        codigo=operacao.get("cliente_codigo") or operacao.get("codigo"),
        tipo_estrutura=operacao.get("tipo_estrutura"),
        ativo_objeto=operacao.get("ativo_objeto"),
        data_fechamento=operacao.get("data_fechamento"),
        data_vencimento=operacao.get("data_vencimento"),
        dias_restantes=dias_restantes if dias_restantes is not None else "N/D",
        strike_1=_ou_nd(operacao.get("strike_1")),
        strike_2=_ou_nd(operacao.get("strike_2")),
        barreira=_ou_nd(operacao.get("barreira")),
        status_barreira=_ou_nd(operacao.get("status_barreira")),
        valor_notional=_ou_nd(operacao.get("valor_notional")),
        motivo_disparo=motivo_disparo,
    )
    return template_str.format_map(contexto).strip()
