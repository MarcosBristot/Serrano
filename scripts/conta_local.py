"""Prepara a pilha local (docker compose) para testar com a SUA conta do Supabase.

    uv run python scripts/conta_local.py [--email voce@exemplo.com] [--org "Fazenda (local)"]

- Lê o ID e o e-mail da sua conta pela API de administração do Supabase (HTTPS; usa a
  SUPABASE_SECRET_KEY do .env) e cria o mesmo usuário no banco local, com uma organização.
  Assim o painel (login pelo Supabase) funciona contra a API local, com dados locais.
- Grava em .token_local (fora do git) um token de DESENVOLVIMENTO assinado com o segredo
  local do docker compose. Ele só vale na API local; serve para scripts como enviar_pendrive.py.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from teste_ponta_a_ponta import ler_env  # noqa: E402

from sistemacampero.domain.tenancy import Organizacao  # noqa: E402
from sistemacampero.infrastructure.persistence.db import Database  # noqa: E402
from sistemacampero.infrastructure.persistence.organizacoes import (  # noqa: E402
    PostgresRepositorioOrganizacoes,
)

ADMIN_LOCAL = "postgresql://postgres:postgres@localhost:54322/campero"
BACKEND_LOCAL = "postgresql://campero_backend:campero_local@localhost:54322/campero"
SEGREDO_LOCAL = "segredo-local-de-desenvolvimento-nao-usar"  # o mesmo do docker-compose.yml


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--email", help="qual conta usar, se houver mais de uma")
    p.add_argument("--org", default="Fazenda Serrano (local)")
    a = p.parse_args()

    env = ler_env()
    r = httpx.get(
        f"{env['SUPABASE_URL']}/auth/v1/admin/users",
        params={"per_page": 100},
        headers={
            "apikey": env["SUPABASE_SECRET_KEY"],
            "Authorization": f"Bearer {env['SUPABASE_SECRET_KEY']}",
        },
        timeout=30,
    )
    r.raise_for_status()
    usuarios = [(u["id"], u.get("email")) for u in r.json()["users"]]
    if a.email:
        usuarios = [u for u in usuarios if (u[1] or "").lower() == a.email.lower()]
    if len(usuarios) != 1:
        print(f"{len(usuarios)} contas encontradas; informe --email.")
        return 1
    uid, email = uuid.UUID(usuarios[0][0]), usuarios[0][1]

    import psycopg

    with psycopg.connect(ADMIN_LOCAL, autocommit=True) as conn:
        conn.execute(
            "insert into auth.users (id, email) values (%s, %s) on conflict (id) do nothing",
            (uid, email),
        )
        tem_org = conn.execute(
            "select 1 from public.membros where usuario_id = %s", (uid,)
        ).fetchone()

    if not tem_org:
        db = Database(BACKEND_LOCAL, min_size=1, max_size=2)
        db.pool.wait(timeout=10)
        org = Organizacao(id=uuid.uuid4(), nome=a.org, slug=f"local-{uuid.uuid4().hex[:8]}")
        PostgresRepositorioOrganizacoes(db).criar_organizacao(org, uid, "basico", 30)
        db.fechar()
        print(f"organização local criada: {a.org}")
    else:
        print("a conta já tem organização no banco local")

    agora = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uid),
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "iss": f"{env['SUPABASE_URL'].rstrip('/')}/auth/v1",
            "iat": agora,
            "exp": agora + 12 * 3600,
        },
        SEGREDO_LOCAL,
        algorithm="HS256",
    )
    destino = Path(__file__).resolve().parents[1] / ".token_local"
    destino.write_text(token, encoding="utf-8")
    print(
        f"conta local pronta ({email}); token de desenvolvimento (12 h) gravado em {destino.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
