"""Teste ponta a ponta com o SEU usuário do Supabase contra a API publicada.

    uv run python scripts/teste_ponta_a_ponta.py https://<sua-api> caminho/arquivo.jdl

Pede e-mail e senha no terminal (a senha não aparece nem é gravada), faz login no
Supabase, cria a organização se ainda não existir, envia o arquivo, espera o
processamento e mostra os indicadores.
"""

from __future__ import annotations

import getpass
import sys
import time
from pathlib import Path

import httpx


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    caminho = Path(__file__).resolve().parents[1] / ".env"
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    api_url, arquivo = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    env = ler_env()
    print(f"/ready: {httpx.get(f'{api_url}/ready', timeout=30).json()}")

    email = input("E-mail do seu usuário no Supabase: ").strip()
    senha = getpass.getpass("Senha (não aparece): ")
    r = httpx.post(
        f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": env["SUPABASE_SECRET_KEY"]},
        json={"email": email, "password": senha},
        timeout=30,
    )
    if r.status_code != 200:
        print(
            "login falhou:", r.status_code, r.json().get("error_description") or r.json().get("msg")
        )
        return 1
    api = httpx.Client(
        base_url=f"{api_url}/api/v1",
        headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        timeout=120,
    )

    me = api.get("/me").json()
    print(f"usuário: {me['email']} | organizações: {[o['nome'] for o in me['organizacoes']]}")
    if not me["organizacoes"]:
        nome = input("Nome da sua organização/fazenda: ").strip() or "Minha Fazenda"
        print(
            "Ao criar a organização você aceita os Termos de Serviço e a Política de Privacidade."
        )
        org = api.post(
            "/organizacoes",
            json={"nome": nome, "aceite_termos": True, "versao_documentos": "2026-10-29"},
        )
        print("organização criada:", org.status_code, org.json().get("slug") or org.json())

    with arquivo.open("rb") as fh:
        up = api.post("/telemetry/upload", files={"arquivo": (arquivo.name, fh)})
    print(
        "upload:", up.status_code, {k: up.json().get(k) for k in ("job_id", "duplicado", "status")}
    )
    job = up.json().get("job_id")
    while job:
        s = api.get(f"/jobs/{job}").json()
        if s["status"] in ("concluido", "morto", "cancelado"):
            print("job:", s["status"], s.get("progresso", {}).get("resultado"), s.get("erro") or "")
            break
        time.sleep(3)

    k = api.get("/kpis/resumo").json()
    print(
        f"KPIs: {k['sessoes']} sessões | motor {k['motor_h']:.2f} h | {k['litros']:.1f} L | "
        f"{k['area_ha']:.2f} ha | L/ha {k['l_ha']} | custo R$ {k['custo_rs']}"
    )
    print("Abra a documentação interativa em:", f"{api_url}/docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
