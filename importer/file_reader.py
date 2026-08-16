"""Leitura de arquivos Excel/CSV exportados manualmente do sistema interno.

Leitura 100% local via pandas + openpyxl. Todas as colunas são lidas como
texto (dtype=str) para evitar que o pandas "adivinhe" tipos e corrompa
silenciosamente valores (datas, números com zero à esquerda, etc.) — a
conversão de tipo é feita de forma explícita e auditável em validators.py.
"""
from pathlib import Path
import pandas as pd


class ArquivoInvalidoError(Exception):
    """Erro estrutural no arquivo (não encontrado, formato não suportado,
    vazio, ou falha de leitura). Interrompe a importação inteira."""


EXTENSOES_SUPORTADAS = (".csv", ".xlsx", ".xls")


def ler_arquivo(caminho) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ArquivoInvalidoError(f"Arquivo não encontrado: {caminho}")
    if not caminho.is_file():
        raise ArquivoInvalidoError(f"Caminho não é um arquivo: {caminho}")

    sufixo = caminho.suffix.lower()
    if sufixo not in EXTENSOES_SUPORTADAS:
        raise ArquivoInvalidoError(
            f"Formato não suportado: '{sufixo}'. Use .csv, .xlsx ou .xls."
        )

    try:
        if sufixo == ".csv":
            df = pd.read_csv(caminho, dtype=str, keep_default_na=False, sep=None, engine="python")
        else:
            df = pd.read_excel(caminho, dtype=str, engine="openpyxl" if sufixo == ".xlsx" else None)
    except Exception as e:  # noqa: BLE001 - queremos capturar qualquer falha de parsing e traduzir
        raise ArquivoInvalidoError(f"Falha ao ler o arquivo '{caminho.name}': {e}") from e

    df = df.fillna("")
    # normaliza nomes de coluna: remove espaços nas pontas
    df.columns = [str(c).strip() for c in df.columns]

    if df.shape[0] == 0:
        raise ArquivoInvalidoError("Arquivo não contém nenhuma linha de dados.")

    return df
