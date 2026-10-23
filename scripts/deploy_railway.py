"""Cria/atualiza o projeto no Railway (serviços api e worker) a partir do .env local.

    uv run python scripts/deploy_railway.py            # cria projeto 'campero' e faz o deploy
    uv run python scripts/deploy_railway.py --so-deploy # só sobe uma nova versão do código

Pré-requisitos: `npx @railway/cli login` feito; .env preenchido (ver docs/deploy.md).
Os segredos vão para o Railway pela entrada padrão (--stdin): nunca aparecem em
argumentos de comando nem são impressos.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLI = [shutil.which("npx") or "npx", "-y", "@railway/cli"]
SEGREDOS = {
    "DATABASE_URL",
    "SUPABASE_SECRET_KEY",
    "CHAVE_CIFRAGEM",
    "SMTP_SENHA",
    "SUPABASE_JWT_SECRET",
}


def rw(*args: str, entrada: str | None = None, checar: bool = True) -> str:
    r = subprocess.run([*CLI, *args], input=entrada, capture_output=True, text=True, cwd=RAIZ)
    if checar and r.returncode != 0:
        sys.exit(f"railway {' '.join(a for a in args[:2])} falhou:\n{r.stderr[-800:]}")
    return r.stdout


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def variaveis(env: dict[str, str], servico: str, ambiente: str) -> dict[str, str]:
    obrig = [
        "SUPABASE_PROJECT_REF",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_POOLER_HOST",
        "CAMPERO_BACKEND_SENHA",
        "CHAVE_CIFRAGEM",
    ]
    faltando = [k for k in obrig if not env.get(k)]
    if faltando:
        sys.exit(f".env incompleto: {', '.join(faltando)}")
    db = (
        f"postgresql://campero_backend.{env['SUPABASE_PROJECT_REF']}:{env['CAMPERO_BACKEND_SENHA']}"
        f"@{env['SUPABASE_POOLER_HOST']}:5432/postgres"
    )
    v = {
        "CAMPERO_SERVICO": servico,
        "AMBIENTE": ambiente,
        "DATABASE_URL": db,
        "SUPABASE_URL": env["SUPABASE_URL"],
        "SUPABASE_SECRET_KEY": env["SUPABASE_SECRET_KEY"],
        "STORAGE_BACKEND": "supabase",
        "CHAVE_CIFRAGEM": env["CHAVE_CIFRAGEM"],
        "LOG_JSON": "true",
        "DB_POOL_MAX": "10" if servico == "api" else "4",
    }
    for opcional in (
        "FRONTEND_URL",
        "SUPABASE_JWT_SECRET",
        "SMTP_HOST",
        "SMTP_PORTA",
        "SMTP_USUARIO",
        "SMTP_SENHA",
        "SMTP_REMETENTE",
    ):
        if env.get(opcional):
            v[opcional] = env[opcional]
    if servico == "api":
        v["CORS_ORIGENS"] = env.get("CORS_ORIGENS") or "[]"
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projeto", default="campero")
    ap.add_argument("--ambiente", default="staging", choices=["dev", "staging", "prod"])
    ap.add_argument("--so-deploy", action="store_true")
    args = ap.parse_args()
    env = ler_env()

    if not args.so_deploy:
        print(f"criando projeto '{args.projeto}'…")
        rw("init", "--name", args.projeto, "--json")
        for servico in ("api", "worker"):
            print(f"serviço {servico}: criando e definindo variáveis…")
            rw("add", "--service", servico, "--json")
            for chave, valor in variaveis(env, servico, args.ambiente).items():
                rw(
                    "variable",
                    "set",
                    chave,
                    "--stdin",
                    "--service",
                    servico,
                    "--skip-deploys",
                    "--json",
                    entrada=valor,
                )
                print(f"  {chave} = {'(segredo)' if chave in SEGREDOS else valor}")

    for servico in ("api", "worker"):
        print(f"deploy de {servico} (build do Dockerfile no Railway)…")
        rw("up", "--service", servico, "--detach")
    dominio = rw("domain", "--service", "api", "--json", checar=False)
    try:
        url = json.loads(dominio).get("domain") or dominio.strip()
    except json.JSONDecodeError:
        url = dominio.strip()
    print(f"\nAPI: https://{url.removeprefix('https://')}  (aguarde o build; depois teste /ready)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
