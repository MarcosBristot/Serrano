"""Supabase Storage via API REST (httpx), sem supabase-py.

Usa a chave secreta do projeto (``SUPABASE_SECRET_KEY``: ``sb_secret_...`` ou a
``service_role`` legada). Os buckets são privados; download só por URL assinada.
"""

from __future__ import annotations

from typing import BinaryIO
from urllib.parse import quote

import httpx


class ErroStorage(RuntimeError):  # noqa: N818 - nomes em português
    pass


class ArmazenamentoSupabase:
    def __init__(self, url: str, chave_secreta: str, cliente: httpx.Client | None = None) -> None:
        self._base = f"{url.rstrip('/')}/storage/v1"
        cabecalhos = {"apikey": chave_secreta}
        if chave_secreta.startswith("eyJ"):  # service_role legada (JWT)
            cabecalhos["Authorization"] = f"Bearer {chave_secreta}"
        self._http = cliente or httpx.Client(timeout=httpx.Timeout(30.0, read=300.0))
        self._http.headers.update(cabecalhos)

    @staticmethod
    def _objeto(bucket: str, caminho: str) -> str:
        return f"{quote(bucket, safe='')}/{quote(caminho, safe='/')}"

    def _checar(self, resp: httpx.Response, operacao: str) -> None:
        if resp.status_code >= 400:
            # Não loga corpo nem cabeçalhos (podem ecoar a chave).
            raise ErroStorage(f"Storage {operacao}: HTTP {resp.status_code}")

    def gravar(self, bucket: str, caminho: str, dados: BinaryIO, content_type: str) -> None:
        resp = self._http.post(
            f"{self._base}/object/{self._objeto(bucket, caminho)}",
            content=iter(lambda: dados.read(1024 * 1024), b""),
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        self._checar(resp, "gravar")

    def ler(self, bucket: str, caminho: str) -> bytes:
        resp = self._http.get(f"{self._base}/object/authenticated/{self._objeto(bucket, caminho)}")
        if resp.status_code in (400, 404):
            raise FileNotFoundError(f"{bucket}/{caminho}")
        self._checar(resp, "ler")
        return resp.content

    def copiar_para(self, bucket: str, caminho: str, destino: BinaryIO) -> None:
        url = f"{self._base}/object/authenticated/{self._objeto(bucket, caminho)}"
        with self._http.stream("GET", url) as resp:
            if resp.status_code in (400, 404):
                raise FileNotFoundError(f"{bucket}/{caminho}")
            self._checar(resp, "copiar_para")
            for parte in resp.iter_bytes(1024 * 1024):
                destino.write(parte)

    def existe(self, bucket: str, caminho: str) -> bool:
        resp = self._http.head(f"{self._base}/object/authenticated/{self._objeto(bucket, caminho)}")
        if resp.status_code in (400, 404):
            return False
        self._checar(resp, "existe")
        return True

    def apagar(self, bucket: str, caminho: str) -> None:
        resp = self._http.request(
            "DELETE", f"{self._base}/object/{quote(bucket, safe='')}", json={"prefixes": [caminho]}
        )
        self._checar(resp, "apagar")

    def url_assinada(self, bucket: str, caminho: str, expira_s: int) -> str:
        resp = self._http.post(
            f"{self._base}/object/sign/{self._objeto(bucket, caminho)}",
            json={"expiresIn": expira_s},
        )
        self._checar(resp, "url_assinada")
        assinado = resp.json().get("signedURL") or resp.json().get("signedUrl")
        if not assinado:
            raise ErroStorage("Storage url_assinada: resposta sem signedURL")
        return f"{self._base}{assinado}" if assinado.startswith("/") else assinado

    def verificar(self) -> None:
        resp = self._http.get(f"{self._base}/bucket/brutos")
        self._checar(resp, "verificar")
