"""Configuração central da aplicação, lida de variáveis de ambiente (.env)."""
import configparser
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CONFIG_DIR = RAIZ_PROJETO / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://jarvis:jarvis@localhost:5432/jarvis"
    secret_key: str = "troque-esta-chave-antes-de-ir-para-producao"
    session_ttl_horas: int = 12
    diretorio_importacoes: str = "./data/importacoes_orbit"
    diretorio_templates_panorama: str = "./templates_mensagens"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def carregar_column_mapping() -> dict:
    """Mapeamento de colunas do arquivo exportado pelo Orbit -> campos internos.

    Configurável em config/column_mapping.ini, sem tocar em código — os nomes
    de coluna aqui são um ponto de partida assumido (padrão do mercado de
    estruturas), não confirmados com uma amostra real do Orbit. Ajuste esse
    .ini no seu ambiente quando tiver o arquivo real em mãos.
    """
    cp = configparser.ConfigParser(interpolation=None)
    caminho = CONFIG_DIR / "column_mapping.ini"
    with open(caminho, "r", encoding="utf-8") as f:
        cp.read_file(f)
    return {
        "colunas": dict(cp["colunas"]),
        "formato_data": cp.get("geral", "formato_data", fallback="%d/%m/%Y"),
        "separador_decimal": cp.get("geral", "separador_decimal", fallback=","),
    }


def carregar_rules_config() -> dict:
    cp = configparser.ConfigParser(interpolation=None)
    caminho = CONFIG_DIR / "rules_config.ini"
    with open(caminho, "r", encoding="utf-8") as f:
        cp.read_file(f)
    return {
        "barreira_proxima_pct": cp.getfloat("barreira", "proxima_pct", fallback=5.0),
        "fixing_alertas_dias_antes": [
            int(x.strip())
            for x in cp.get("fixing", "alertas_dias_antes", fallback="5,2,1,0").split(",")
            if x.strip()
        ],
        "vencimento_alertas_dias_antes": [
            int(x.strip())
            for x in cp.get("vencimento", "alertas_dias_antes", fallback="30,15,5").split(",")
            if x.strip()
        ],
    }
