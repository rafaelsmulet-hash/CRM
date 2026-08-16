"""Leitura de arquivos CSV exportados manualmente do sistema interno.

Usa exclusivamente o módulo `csv` da biblioteca padrão do Python — sem
pandas, sem openpyxl, sem nenhuma dependência de terceiros. Isso permite
rodar o sistema em uma máquina 100% air-gapped sem NENHUMA instalação via
rede: basta ter o Python 3.11+ instalado.

Suporta apenas .csv (não .xlsx). Se o seu sistema interno exporta apenas em
Excel, use "Salvar como... > CSV (separado por vírgulas)" antes de importar
— é uma etapa manual de poucos segundos, e mantém o sistema livre de
dependências de bibliotecas de terceiros para leitura de planilhas
binárias, que são uma superfície de risco maior num contexto de compliance.
"""
import csv
from pathlib import Path


class ArquivoInvalidoError(Exception):
    """Erro estrutural no arquivo (não encontrado, formato não suportado,
    vazio, sem cabeçalho, ou falha de leitura). Interrompe a importação inteira."""


EXTENSOES_SUPORTADAS = (".csv",)


def ler_arquivo(caminho) -> tuple[list[str], list[dict]]:
    """Lê um arquivo CSV e retorna (colunas, linhas), onde `linhas` é uma
    lista de dicts {nome_da_coluna: valor_em_texto}."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ArquivoInvalidoError(f"Arquivo não encontrado: {caminho}")
    if not caminho.is_file():
        raise ArquivoInvalidoError(f"Caminho não é um arquivo: {caminho}")

    sufixo = caminho.suffix.lower()
    if sufixo not in EXTENSOES_SUPORTADAS:
        raise ArquivoInvalidoError(
            f"Formato não suportado: '{sufixo}'. Use .csv "
            "(no Excel: Salvar como... > CSV separado por vírgulas)."
        )

    try:
        # utf-8-sig remove o BOM que o Excel costuma gravar em CSVs no Windows.
        with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            try:
                dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
            except csv.Error:
                dialeto = csv.excel  # fallback: vírgula, como um CSV "padrão"
            leitor = csv.DictReader(f, dialect=dialeto)
            colunas = leitor.fieldnames
            if not colunas:
                raise ArquivoInvalidoError("Arquivo não contém linha de cabeçalho.")
            colunas = [c.strip() if c else c for c in colunas]

            linhas = []
            for linha_bruta in leitor:
                linha = {
                    (chave.strip() if chave else chave): (valor.strip() if isinstance(valor, str) else valor)
                    for chave, valor in linha_bruta.items()
                }
                linhas.append(linha)
    except ArquivoInvalidoError:
        raise
    except UnicodeDecodeError as e:
        raise ArquivoInvalidoError(
            f"Falha ao ler o arquivo '{caminho.name}': codificação inválida (use UTF-8). Detalhe: {e}"
        ) from e
    except Exception as e:  # noqa: BLE001 - traduz qualquer falha de parsing para o tipo de erro do domínio
        raise ArquivoInvalidoError(f"Falha ao ler o arquivo '{caminho.name}': {e}") from e

    if not linhas:
        raise ArquivoInvalidoError("Arquivo não contém nenhuma linha de dados.")

    return colunas, linhas
