"""Ingestão: arquivos brutos, lotes e jobs (fila durável)."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

BUCKET_BRUTOS = "brutos"  # imutável: brutos/<org>/<sha256>.<ext>
BUCKET_LIMPOS = "limpos"  # Parquet 1 Hz: limpos/<org>/<sha256>.parquet
BUCKET_EXPORTACOES = "exportacoes"


class TipoJob(StrEnum):
    EXPANDIR_ZIP = "expandir_zip"
    IMPORTAR_GEN4 = "importar_gen4"
    PROCESSAR_ARQUIVO = "processar_arquivo"


# Menor = antes: zip -> cadastro do monitor (talhões) -> .jdl (já localiza por GPS).
PRIORIDADE: dict[TipoJob, int] = {
    TipoJob.EXPANDIR_ZIP: 50,
    TipoJob.IMPORTAR_GEN4: 60,
    TipoJob.PROCESSAR_ARQUIVO: 100,
}


class StatusJob(StrEnum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    CONCLUIDO = "concluido"
    ERRO = "erro"
    MORTO = "morto"  # esgotou as tentativas (dead-letter)
    CANCELADO = "cancelado"


class StatusArquivo(StrEnum):
    RECEBIDO = "recebido"
    PROCESSANDO = "processando"
    PROCESSADO = "processado"
    VAZIO = "vazio"
    REJEITADO = "rejeitado"
    ERRO = "erro"
    BLOQUEADO_PLANO = "bloqueado_plano"


class TipoArquivo(StrEnum):
    JDL = "jdl"
    ZIP = "zip"
    MASTERDATA = "masterdata"
    GJSON = "gjson"


_EXTENSOES = {".jdl": TipoArquivo.JDL, ".zip": TipoArquivo.ZIP, ".gjson": TipoArquivo.GJSON}


def tipo_do_arquivo(nome: str) -> TipoArquivo | None:
    """Pelo nome (o conteúdo é validado depois pelo adapter)."""
    base = posixpath.basename(nome.replace("\\", "/"))
    if base.lower() == "masterdata.xml":
        return TipoArquivo.MASTERDATA
    _, ext = posixpath.splitext(base.lower())
    return _EXTENSOES.get(ext)


_INSEGURO = re.compile(r"[^\w.\-\[\]{}() ,]+", re.UNICODE)


def nome_para_exibicao(nome: str) -> str:
    """Nome do cliente só para exibição: sem diretórios nem caracteres de controle."""
    base = posixpath.basename(nome.replace("\\", "/")).strip()
    return (_INSEGURO.sub("_", base) or "arquivo")[:200]


def caminho_bruto(organizacao_id: UUID, sha256: str, tipo: TipoArquivo) -> str:
    """O nome do cliente nunca vira caminho: brutos/<org>/<sha256>.<ext>."""
    ext = "xml" if tipo is TipoArquivo.MASTERDATA else tipo.value
    return f"{organizacao_id}/{sha256}.{ext}"


def caminho_limpo(organizacao_id: UUID, sha256: str) -> str:
    return f"{organizacao_id}/{sha256}.parquet"


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    organizacao_id: UUID
    tipo: TipoJob
    payload: dict[str, Any]
    tentativas: int
    max_tentativas: int
    lote_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ArquivoRegistrado:
    arquivo_id: UUID
    job_id: UUID | None
    duplicado: bool
    status: StatusArquivo


@dataclass(frozen=True, slots=True)
class NovoArquivo:
    organizacao_id: UUID
    sha256: str
    nome_original: str
    tipo: TipoArquivo
    tamanho_bytes: int
    caminho_storage: str
    marca: str | None = None
    tecnologia: str | None = None
    lote_id: UUID | None = None
    arquivo_pai_id: UUID | None = None


@dataclass(slots=True)
class SituacaoJob:
    id: UUID
    tipo: str
    status: str
    tentativas: int
    max_tentativas: int
    progresso: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None
    arquivo_id: UUID | None = None
    lote_id: UUID | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None


class Cancelado(Exception):  # noqa: N818 - sinal de controle, não erro
    """O job teve cancelamento solicitado; o handler para entre etapas."""
