"""Leitura e validação do arquivo exportado pelo Orbit — funções puras.

Mesmo padrão do `importer/file_reader.py` + `importer/validators.py` do
Jarvis CLI: erro estrutural (arquivo vazio, sem cabeçalho, coluna
obrigatória ausente) aborta a importação inteira e nada é gravado; erro
numa linha (campo obrigatório vazio/inválido) descarta só aquela linha.
"""
import csv
import dataclasses
import datetime
import io

import openpyxl

CAMPOS_OBRIGATORIOS = [
    "cliente_nome",
    "operacao_ref",
    "tipo_estrutura",
    "ativo_principal",
    "data_inicio",
    "data_vencimento",
]

CAMPOS_OPCIONAIS = [
    "cliente_codigo",
    "notional",
    "moeda",
    "valor_entrada",
    "barreira_1_nivel",
    "barreira_1_tipo",
    "barreira_1_regra_observacao",
    "fixing_1_data",
    "fixing_1_tipo",
    "preco_ativo",
    "preco_data",
]

TODOS_CAMPOS = CAMPOS_OBRIGATORIOS + CAMPOS_OPCIONAIS


class ErroEstrutural(Exception):
    """Aborta a importação inteira — nada é gravado no banco."""


@dataclasses.dataclass
class LinhaValidada:
    numero_linha: int
    dados: dict
    avisos: list[str]


@dataclasses.dataclass
class ErroLinha:
    numero_linha: int
    motivo: str


@dataclasses.dataclass
class ResultadoParsing:
    linhas: list[LinhaValidada]
    erros: list[ErroLinha]


def ler_linhas_brutas(conteudo: bytes, nome_arquivo: str) -> list[dict]:
    """Lê .xlsx ou .csv e devolve uma lista de dicts (cabeçalho -> valor)."""
    if nome_arquivo.lower().endswith(".xlsx"):
        return _ler_xlsx(conteudo)
    if nome_arquivo.lower().endswith(".csv"):
        return _ler_csv(conteudo)
    raise ErroEstrutural(f"Formato não suportado: {nome_arquivo!r}. Use .xlsx ou .csv.")


def _ler_xlsx(conteudo: bytes) -> list[dict]:
    try:
        planilha = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — arquivo corrompido/ilegível é sempre erro estrutural
        raise ErroEstrutural(f"Não foi possível abrir o arquivo .xlsx: {exc}") from exc

    aba = planilha.active
    linhas = list(aba.iter_rows(values_only=True))
    if not linhas:
        raise ErroEstrutural("Arquivo vazio.")

    cabecalho = [str(c).strip() if c is not None else "" for c in linhas[0]]
    if not any(cabecalho):
        raise ErroEstrutural("Arquivo sem cabeçalho.")

    return [
        dict(zip(cabecalho, linha))
        for linha in linhas[1:]
        if any(v is not None and str(v).strip() != "" for v in linha)
    ]


def _ler_csv(conteudo: bytes) -> list[dict]:
    texto = conteudo.decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto))
    if not leitor.fieldnames:
        raise ErroEstrutural("Arquivo sem cabeçalho.")
    linhas = [linha for linha in leitor if any((v or "").strip() for v in linha.values())]
    if not linhas:
        raise ErroEstrutural("Arquivo vazio.")
    return linhas


def _parse_data(valor: str | datetime.date | datetime.datetime | None, formato: str) -> datetime.date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    return datetime.datetime.strptime(str(valor).strip(), formato).date()


def _parse_numero(valor, separador_decimal: str) -> float | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if separador_decimal == ",":
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def mapear_e_validar(
    linhas_brutas: list[dict], mapeamento: dict, formato_data: str, separador_decimal: str
) -> ResultadoParsing:
    colunas = mapeamento  # campo_interno -> nome_da_coluna_no_arquivo

    faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in colunas]
    if faltando:
        raise ErroEstrutural(
            f"config/column_mapping.ini não mapeia os campos obrigatórios: {', '.join(faltando)}."
        )

    if linhas_brutas:
        colunas_do_arquivo = set(linhas_brutas[0].keys())
        mapeadas_ausentes = [
            f"{campo} (esperava coluna {colunas[campo]!r})"
            for campo in CAMPOS_OBRIGATORIOS
            if colunas[campo] not in colunas_do_arquivo
        ]
        if mapeadas_ausentes:
            raise ErroEstrutural(
                "Colunas obrigatórias não encontradas no arquivo — ajuste config/column_mapping.ini: "
                + "; ".join(mapeadas_ausentes)
            )

    linhas_ok: list[LinhaValidada] = []
    erros: list[ErroLinha] = []

    for indice, linha_bruta in enumerate(linhas_brutas, start=2):  # linha 1 = cabeçalho
        try:
            dados: dict = {}
            avisos: list[str] = []

            for campo in CAMPOS_OBRIGATORIOS:
                valor_bruto = linha_bruta.get(colunas[campo])
                if valor_bruto is None or str(valor_bruto).strip() == "":
                    raise ValueError(f"campo obrigatório {campo!r} vazio")
                dados[campo] = str(valor_bruto).strip()

            dados["data_inicio"] = _parse_data(dados["data_inicio"], formato_data)
            dados["data_vencimento"] = _parse_data(dados["data_vencimento"], formato_data)

            for campo in CAMPOS_OPCIONAIS:
                coluna = colunas.get(campo)
                valor_bruto = linha_bruta.get(coluna) if coluna else None
                if valor_bruto is None or str(valor_bruto).strip() == "":
                    dados[campo] = None
                    continue
                try:
                    if campo in ("notional", "valor_entrada", "barreira_1_nivel", "preco_ativo"):
                        dados[campo] = _parse_numero(valor_bruto, separador_decimal)
                    elif campo in ("fixing_1_data", "preco_data"):
                        dados[campo] = _parse_data(valor_bruto, formato_data)
                    else:
                        dados[campo] = str(valor_bruto).strip()
                except ValueError:
                    avisos.append(f"campo opcional {campo!r} inválido ({valor_bruto!r}) — ignorado")
                    dados[campo] = None

            linhas_ok.append(LinhaValidada(numero_linha=indice, dados=dados, avisos=avisos))
        except ValueError as exc:
            erros.append(ErroLinha(numero_linha=indice, motivo=str(exc)))

    return ResultadoParsing(linhas=linhas_ok, erros=erros)
