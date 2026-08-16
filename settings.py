"""Carregamento centralizado de configuração (YAML) e resolução de caminhos.

Nenhuma chamada de rede é feita neste módulo nem em nenhum outro do projeto.
Todos os arquivos de configuração são locais e editáveis manualmente.
"""
from pathlib import Path
import yaml

RAIZ_PROJETO = Path(__file__).parent
CONFIG_DIR = RAIZ_PROJETO / "config"


def _carregar_yaml(nome_arquivo: str) -> dict:
    caminho = CONFIG_DIR / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def carregar_settings() -> dict:
    dados = _carregar_yaml("settings.yaml")
    dados["_db_path_absoluto"] = str(RAIZ_PROJETO / dados["db_path"])
    dados["_inbox_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_inbox"])
    dados["_processados_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_processados"])
    dados["_backups_absoluto"] = str(RAIZ_PROJETO / dados["diretorio_backups"])
    return dados


def carregar_column_mapping() -> dict:
    return _carregar_yaml("column_mapping.yaml")


def carregar_rules_config() -> dict:
    return _carregar_yaml("rules_config.yaml")
