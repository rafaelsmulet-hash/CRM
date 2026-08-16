"""Carregamento centralizado de configuração e resolução de caminhos.

Usa exclusivamente `configparser`, da biblioteca padrão do Python — nenhuma
dependência de terceiros, nenhuma chamada de rede, em nenhum módulo deste
projeto.
"""
import configparser
from pathlib import Path

RAIZ_PROJETO = Path(__file__).parent
CONFIG_DIR = RAIZ_PROJETO / "config"


def _ler_ini(nome_arquivo: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    caminho = CONFIG_DIR / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        cp.read_file(f)
    return cp


def carregar_settings() -> dict:
    cp = _ler_ini("settings.ini")
    sec = cp["caminhos"]
    dados = {
        "db_path": sec["db_path"],
        "diretorio_inbox": sec["diretorio_inbox"],
        "diretorio_processados": sec["diretorio_processados"],
        "diretorio_backups": sec["diretorio_backups"],
    }
    dados["_db_path_absoluto"] = str(RAIZ_PROJETO / dados["db_path"])
    dados["_inbox_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_inbox"])
    dados["_processados_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_processados"])
    dados["_backups_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_backups"])
    return dados


def carregar_column_mapping() -> dict:
    cp = _ler_ini("column_mapping.ini")
    return {
        "colunas": dict(cp["colunas"]),
        "formato_data": cp.get("geral", "formato_data", fallback="%d/%m/%Y"),
        "separador_decimal": cp.get("geral", "separador_decimal", fallback=","),
    }


def _lista_int(valor: str) -> list[int]:
    return [int(x.strip()) for x in valor.split(",") if x.strip()]


def _lista_str(valor: str) -> list[str]:
    return [x.strip() for x in valor.split(",") if x.strip()]


def carregar_rules_config() -> dict:
    cp = _ler_ini("rules_config.ini")
    return {
        "regra_tempo_decorrido": {
            "ativa": cp.getboolean("regra_tempo_decorrido", "ativa", fallback=True),
            "meses": _lista_int(cp.get("regra_tempo_decorrido", "meses", fallback="1,3,6,12")),
        },
        "regra_vencimento_proximo": {
            "ativa": cp.getboolean("regra_vencimento_proximo", "ativa", fallback=True),
            "dias_antes": _lista_int(cp.get("regra_vencimento_proximo", "dias_antes", fallback="30,15,5")),
        },
        "regra_evento_barreira": {
            "ativa": cp.getboolean("regra_evento_barreira", "ativa", fallback=True),
            "status_relevantes": _lista_str(cp.get("regra_evento_barreira", "status_relevantes", fallback="")),
        },
    }
