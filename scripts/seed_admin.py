"""Cria o primeiro usuário admin. Rode uma vez, após as migrações.

    python scripts/seed_admin.py voce@corretora.com "Seu Nome" "senha-temporaria"

Troque a senha no primeiro acesso — este script não tem tela, é só bootstrap.
"""
import sys

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Papel, Usuario  # noqa: E402
from app.security import hash_senha  # noqa: E402


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(1)

    email, nome, senha = sys.argv[1], sys.argv[2], sys.argv[3]
    db = SessionLocal()
    try:
        if db.scalar(select(Usuario).where(Usuario.email == email.lower())):
            print(f"Usuário {email} já existe.")
            return
        db.add(
            Usuario(
                nome=nome,
                email=email.strip().lower(),
                senha_hash=hash_senha(senha),
                papel=Papel.admin,
                ativo=True,
            )
        )
        db.commit()
        print(f"Usuário admin {email} criado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
