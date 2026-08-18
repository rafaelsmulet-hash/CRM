from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.deps import RedirecionarParaLogin
from app.routers import alertas, auditoria, auth, calendario, clientes, dashboard, estruturas, orbit, panoramas

app = FastAPI(title="Jarvis — Monitoramento de Estruturas de Derivativos")

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web" / "static")), name="static")


@app.exception_handler(RedirecionarParaLogin)
async def redirecionar_login(request: Request, exc: RedirecionarParaLogin):
    return RedirectResponse(url="/auth/login", status_code=303)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(clientes.router)
app.include_router(estruturas.router)
app.include_router(orbit.router)
app.include_router(calendario.router)
app.include_router(alertas.router)
app.include_router(panoramas.router)
app.include_router(auditoria.router)
