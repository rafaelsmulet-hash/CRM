"""Instância única do Jinja2Templates, compartilhada por todos os routers."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
