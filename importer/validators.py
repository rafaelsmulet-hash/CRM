"""Validação e conversão de tipos linha a linha (tratamento de erros).

Filosofia: erros em campos OBRIGATÓRIOS derrubam a linha inteira (ela não é
importada, e o motivo fica registrado em log_importacoes.detalhes).
Erros em campos OPCIONAIS não derrubam a linha: o campo fica None e um aviso
é registrado, mas a operação continua sendo importada — clareza de auditoria
é priorizada sobre "esconder" dados incompletos.
"""
import hashlib
import unicodedata
from datetime import date, datetime

CAMPOS_OBRIGATORIOS = [
    "cliente_id", "nome", "tipo_estrutura", "ativo_objeto",
    "data_fechamento", "data_vencimento",
]
CAMPOS_DATA = ["data_fechamento", "data_vencimento"]
CAMPOS_NUMERICOS_OPCIONAIS = ["strike_1", "strike_2", "barreira", "valor_notional"]
CAMPOS_TEXTO_OPCIONAIS = ["operacao_id", "status_barreira", "perfil_suitability"]

TODOS_OS_CAMPOS = CAMPOS_OBRIGATORIOS + CAMPOS_TEXTO_OPCIONAIS + CAMPOS_NUMERICOS_OPCIONAIS


class LinhaInvalidaError(Exception):
    """Linha não pôde ser importada por falta/invalidade de campo obrigatório."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def normalizar_texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def slugify(valor: str) -> str:
    """Normaliza texto para comparação/chave: minúsculas, sem acento, '_' no lugar de espaço."""
    valor = normalizar_texto(valor).lower()
    nfkd = unicodedata.normalize("NFKD", valor)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "_".join(sem_acento.split())


def validar_colunas_presentes(colunas_arquivo, mapeamento: dict) -> list[str]:
    """Confere se todas as colunas OBRIGATÓRIAS mapeadas existem no arquivo.
    Retorna lista de nomes de coluna (do arquivo) que faltam."""
    colunas_arquivo = set(colunas_arquivo)
    faltando = []
    for campo in CAMPOS_OBRIGATORIOS:
        nome_coluna_arquivo = mapeamento.get(campo)
        if not nome_coluna_arquivo or nome_coluna_arquivo not in colunas_arquivo:
            faltando.append(f"{campo} (esperado como coluna '{nome_coluna_arquivo}')")
    return faltando


def parse_data(valor: str, formato: str) -> date | None:
    valor = normalizar_texto(valor)
    if not valor:
        return None
    try:
        return datetime.strptime(valor, formato).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def parse_numero(valor: str, separador_decimal: str = ",") -> float | None:
    valor = normalizar_texto(valor)
    if not valor:
        return None
    bruto = valor
    if separador_decimal == ",":
        # formato BR: pontos são separador de milhar, vírgula é decimal
        valor = valor.replace(".", "").replace(",", ".")
    else:
        # formato internacional: vírgulas são separador de milhar
        valor = valor.replace(",", "")
    try:
        return float(valor)
    except ValueError:
        raise ValueError(f"valor numérico inválido: '{bruto}'")


def gerar_operacao_ref_sintetico(cliente_id: str, tipo_estrutura: str, ativo_objeto: str,
                                  data_fechamento: str, strike_1: str, strike_2: str,
                                  barreira: str) -> str:
    """Gera um ID estável quando o arquivo de origem não traz operacao_id.
    Baseado em campos que identificam a operação; se algum desses campos
    mudar entre importações, o sistema tratará como uma operação diferente
    (limitação documentada no README)."""
    base = "|".join([
        normalizar_texto(cliente_id), normalizar_texto(tipo_estrutura),
        normalizar_texto(ativo_objeto), normalizar_texto(data_fechamento),
        normalizar_texto(strike_1), normalizar_texto(strike_2), normalizar_texto(barreira),
    ])
    return "SINT-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def extrair_linha(linha_bruta: dict, mapeamento: dict, formato_data: str,
                   separador_decimal: str) -> tuple[dict | None, list[str]]:
    """Converte uma linha bruta (dict coluna_arquivo -> valor) em um registro
    canônico. Retorna (registro, avisos). Levanta LinhaInvalidaError se algum
    campo obrigatório estiver ausente ou inválido."""
    avisos: list[str] = []

    def valor_bruto(campo_canonico):
        coluna = mapeamento.get(campo_canonico)
        if not coluna:
            return ""
        return linha_bruta.get(coluna, "")

    registro = {}

    for campo in CAMPOS_OBRIGATORIOS:
        bruto = normalizar_texto(valor_bruto(campo))
        if not bruto:
            raise LinhaInvalidaError(f"campo obrigatório ausente/vazio: '{campo}'")
        registro[campo] = bruto

    for campo in CAMPOS_DATA:
        parsed = parse_data(registro[campo], formato_data)
        if parsed is None:
            raise LinhaInvalidaError(
                f"campo obrigatório '{campo}' com data inválida: '{registro[campo]}' "
                f"(formato esperado: {formato_data})"
            )
        registro[campo] = parsed

    for campo in CAMPOS_TEXTO_OPCIONAIS:
        registro[campo] = normalizar_texto(valor_bruto(campo)) or None

    for campo in CAMPOS_NUMERICOS_OPCIONAIS:
        bruto = normalizar_texto(valor_bruto(campo))
        if not bruto:
            registro[campo] = None
            continue
        try:
            registro[campo] = parse_numero(bruto, separador_decimal)
        except ValueError as e:
            avisos.append(f"campo opcional '{campo}' ignorado: {e}")
            registro[campo] = None

    if not registro.get("operacao_id"):
        registro["operacao_id"] = gerar_operacao_ref_sintetico(
            registro["cliente_id"], registro["tipo_estrutura"], registro["ativo_objeto"],
            str(registro["data_fechamento"]), str(registro.get("strike_1") or ""),
            str(registro.get("strike_2") or ""), str(registro.get("barreira") or ""),
        )
        avisos.append(
            f"operacao_id ausente no arquivo; ID sintético gerado: {registro['operacao_id']}"
        )

    return registro, avisos
