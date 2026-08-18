"""Roda o avaliador de regras manualmente, sem precisar reimportar o Orbit.

Útil para cron (produção) ou para reprocessar uma data específica em dev:

    python scripts/run_motor.py [YYYY-MM-DD]
"""
import datetime
import sys

sys.path.insert(0, ".")

from app.db import SessionLocal  # noqa: E402
from app.services import motor  # noqa: E402


def main() -> None:
    data_referencia = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    db = SessionLocal()
    try:
        log = motor.executar(db, data_referencia=data_referencia)
        db.commit()
        print(
            f"Motor executado para {log.data_execucao}: "
            f"{log.estruturas_processadas} estrutura(s), {log.eventos_gerados} evento(s), "
            f"{len(log.erros)} erro(s)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
