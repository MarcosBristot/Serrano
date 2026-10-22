"""Storage em disco (dev, docker-compose e testes). Mesma semântica do Supabase Storage."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

_SEGMENTO = re.compile(r"^[A-Za-z0-9._-]+$")


class ArmazenamentoLocal:
    def __init__(self, raiz: Path, segredo_url: bytes | None = None) -> None:
        self._raiz = raiz.resolve()
        self._raiz.mkdir(parents=True, exist_ok=True)
        self._segredo = segredo_url or os.urandom(32)

    def _caminho(self, bucket: str, caminho: str) -> Path:
        partes = [bucket, *caminho.split("/")]
        if not all(_SEGMENTO.fullmatch(p) and p not in (".", "..") for p in partes):
            raise ValueError(f"caminho inválido no storage: {bucket}/{caminho}")
        alvo = self._raiz.joinpath(*partes).resolve()
        if self._raiz not in alvo.parents:
            raise ValueError("caminho fora do storage")
        return alvo

    def gravar(self, bucket: str, caminho: str, dados: BinaryIO, content_type: str) -> None:
        alvo = self._caminho(bucket, caminho)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: arquivo temporário + rename.
        with tempfile.NamedTemporaryFile(dir=alvo.parent, delete=False) as tmp:
            shutil.copyfileobj(dados, tmp, 1024 * 1024)
        os.replace(tmp.name, alvo)

    def ler(self, bucket: str, caminho: str) -> bytes:
        alvo = self._caminho(bucket, caminho)
        if not alvo.is_file():
            raise FileNotFoundError(f"{bucket}/{caminho}")
        return alvo.read_bytes()

    def copiar_para(self, bucket: str, caminho: str, destino: BinaryIO) -> None:
        alvo = self._caminho(bucket, caminho)
        if not alvo.is_file():
            raise FileNotFoundError(f"{bucket}/{caminho}")
        with alvo.open("rb") as origem:
            shutil.copyfileobj(origem, destino, 1024 * 1024)

    def existe(self, bucket: str, caminho: str) -> bool:
        return self._caminho(bucket, caminho).is_file()

    def apagar(self, bucket: str, caminho: str) -> None:
        self._caminho(bucket, caminho).unlink(missing_ok=True)

    def url_assinada(self, bucket: str, caminho: str, expira_s: int) -> str:
        self._caminho(bucket, caminho)
        expira = int(time.time()) + expira_s
        msg = f"{bucket}/{caminho}:{expira}".encode()
        assinatura = hmac.new(self._segredo, msg, hashlib.sha256).hexdigest()[:32]
        return f"local://{bucket}/{caminho}?expira={expira}&assinatura={assinatura}"

    def verificar(self) -> None:
        if not os.access(self._raiz, os.W_OK):
            raise PermissionError(f"sem escrita em {self._raiz}")
