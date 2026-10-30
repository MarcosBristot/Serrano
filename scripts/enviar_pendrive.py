"""Envia o conteúdo de um pendrive do monitor (Gen4 + JD-Data) para a sua organização.

    uv run python scripts/enviar_pendrive.py http://localhost:8000 "C:/caminho/do/pendrive"
    uv run python scripts/enviar_pendrive.py http://localhost:8000 "C:/pendrive" --limite 50

Pede e-mail e senha no terminal (a senha não aparece nem é gravada). Envia primeiro a pasta
Gen4 compactada (talhões e contornos), depois os arquivos .jdl em ordem de data, alguns em
paralelo. Pode ser executado de novo: arquivos já enviados voltam como "duplicado" sem custo.
No fim, acompanha o processamento do lote e mostra o resumo.
"""

from __future__ import annotations

import argparse
import getpass
import io
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teste_ponta_a_ponta import ler_env  # noqa: E402


class Sessao:
    """Token do Supabase com renovação automática (o envio pode passar de 1 hora)."""

    def __init__(self, supabase_url: str, chave: str) -> None:
        self._url = supabase_url
        self._chave = chave
        self._lock = threading.Lock()
        self.token = ""
        self._renovar = ""
        self._expira = 0.0

    def entrar(self, email: str, senha: str) -> None:
        self._guardar(self._pedir("password", {"email": email, "password": senha}))

    def usar_token(self, token: str) -> None:
        """Token fixo (desenvolvimento local): sem renovação."""
        self.token, self._expira = token, float("inf")

    def _pedir(self, tipo: str, corpo: dict[str, str]) -> dict[str, Any]:
        r = httpx.post(
            f"{self._url}/auth/v1/token?grant_type={tipo}",
            headers={"apikey": self._chave},
            json=corpo,
            timeout=30,
        )
        if r.status_code != 200:
            raise SystemExit(f"login falhou ({r.status_code}): {r.text[:200]}")
        return r.json()  # type: ignore[no-any-return]

    def _guardar(self, dados: dict[str, Any]) -> None:
        self.token = dados["access_token"]
        self._renovar = dados["refresh_token"]
        self._expira = time.time() + float(dados.get("expires_in", 3600)) - 120

    def cabecalhos(self, org: str | None = None) -> dict[str, str]:
        with self._lock:
            if time.time() > self._expira:
                self._guardar(self._pedir("refresh_token", {"refresh_token": self._renovar}))
            h = {"Authorization": f"Bearer {self.token}"}
        if org:
            h["X-Organizacao-Id"] = org
        return h


def zip_gen4(pasta: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in pasta.rglob("*"):
            if f.is_file():
                zf.write(f, f"Gen4/{f.relative_to(pasta).as_posix()}")
    return buf.getvalue()


def enviar(
    cli: httpx.Client, sessao: Sessao, org: str, nome: str, dados: bytes, lote: str | None
) -> dict[str, Any]:
    params = {"marca": "john_deere", "tecnologia": "gen4", **({"lote_id": lote} if lote else {})}
    for tentativa in range(8):
        try:
            r = cli.post(
                "/telemetry/upload",
                params=params,
                files={"arquivo": (nome, dados, "application/octet-stream")},
                headers=sessao.cabecalhos(org),
            )
        except httpx.TransportError:
            time.sleep(2 + tentativa * 3)
            continue
        if r.status_code == 429:  # limite de uploads por minuto: espera o que a API pedir
            time.sleep(float(r.headers.get("retry-after", "5")))
            continue
        if r.status_code >= 500:
            time.sleep(2 + tentativa * 3)
            continue
        return {"status_http": r.status_code, **(r.json() if r.content else {})}
    return {"status_http": 0, "erro": "sem resposta após várias tentativas"}


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("api", help="ex.: http://localhost:8000")
    p.add_argument("pendrive", type=Path, help="pasta que contém Gen4 e/ou JD-Data")
    p.add_argument("--limite", type=int, default=0, help="envia só os N primeiros .jdl (teste)")
    p.add_argument("--pasta", default="", help="só .jdl cujo caminho contém este texto")
    p.add_argument("--paralelo", type=int, default=3)
    p.add_argument("--sem-gen4", action="store_true", help="não envia a pasta Gen4")
    p.add_argument("--sem-esperar", action="store_true", help="não acompanha o processamento")
    p.add_argument(
        "--token-local",
        action="store_true",
        help="token de desenvolvimento de .token_local (só pilha local; ver conta_local.py)",
    )
    a = p.parse_args()

    raiz: Path = a.pendrive
    jdls = sorted(f for f in raiz.rglob("*.jdl") if a.pasta.lower() in str(f).lower())
    if a.limite:
        jdls = jdls[: a.limite]
    gen4 = next((d for d in raiz.rglob("Gen4") if d.is_dir()), None)
    total_mb = sum(f.stat().st_size for f in jdls) / 1024**2
    print(
        f"{len(jdls)} arquivos .jdl ({total_mb:.0f} MB)"
        + (f" + pasta Gen4 ({gen4})" if gen4 else "")
    )

    env = ler_env()
    api_url = a.api.rstrip("/")
    print(f"/ready: {httpx.get(f'{api_url}/ready', timeout=30).json().get('status')}")
    sessao = Sessao(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    if a.token_local:
        sessao.usar_token(
            (Path(__file__).resolve().parents[1] / ".token_local").read_text().strip()
        )
    else:
        sessao.entrar(
            input("E-mail do seu usuário: ").strip(), getpass.getpass("Senha (não aparece): ")
        )

    cli = httpx.Client(base_url=f"{api_url}/api/v1", timeout=600)
    me = cli.get("/me", headers=sessao.cabecalhos()).json()
    if not me.get("organizacoes"):
        print("Crie a organização pelo painel antes de enviar.")
        return 1
    org = me["organizacoes"][0]["organizacao_id"]
    print(f"organização: {me['organizacoes'][0]['nome']}")

    if gen4 and not a.sem_gen4:
        r = enviar(cli, sessao, org, "Gen4.zip", zip_gen4(gen4), None)
        print(f"Gen4 (talhões): {r.get('status') or r}")

    lote = cli.post("/batches", headers=sessao.cabecalhos(org)).json()["lote_id"]
    contagem = {"novo": 0, "duplicado": 0, "erro": 0}
    inicio = time.time()
    with ThreadPoolExecutor(max_workers=a.paralelo) as pool:
        # cada arquivo é lido só na hora do envio (não carrega o pendrive inteiro na memória)
        futuros = {
            pool.submit(lambda f: enviar(cli, sessao, org, f.name, f.read_bytes(), lote), f): f
            for f in jdls
        }
        for i, fut in enumerate(as_completed(futuros), 1):
            r = fut.result()
            if r.get("status_http") != 202:
                contagem["erro"] += 1
                print(f"\n  erro em {futuros[fut].name}: {r}")
            else:
                contagem["duplicado" if r.get("duplicado") else "novo"] += 1
            if i % 10 == 0 or i == len(jdls):
                taxa = i / max(time.time() - inicio, 1)
                print(
                    f"\r  enviados {i}/{len(jdls)}  {contagem}"
                    f"  ~{(len(jdls) - i) / taxa / 60:.0f} min restantes   ",
                    end="",
                )
    print()

    if a.sem_esperar:
        print(f"lote {lote}: acompanhe no painel (Enviar pendrive / Operações).")
        return 0
    print("processando (o worker segue em segundo plano; pode fechar com Ctrl+C quando quiser)")
    while True:
        s = cli.get(f"/batches/{lote}", headers=sessao.cabecalhos(org)).json()
        print(
            f"\r  processados {s['processados']} · vazios {s['vazios']} · com erro {s['com_erro']}"
            f" · bloqueados {s['bloqueados']} · pendentes {s['pendentes']}   ",
            end="",
        )
        if s["pendentes"] == 0:
            break
        time.sleep(10)
    print()
    resumo = cli.get("/kpis/resumo", headers=sessao.cabecalhos(org)).json()
    print(
        f"resumo: {resumo.get('sessoes')} operações · {resumo.get('maquinas')} máquinas"
        f" · {resumo.get('motor_h') or 0:.1f} h · {resumo.get('litros') or 0:.0f} L"
        f" · {resumo.get('area_ha') or 0:.1f} ha"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
