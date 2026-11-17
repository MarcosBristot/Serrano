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
    EXPORTAR = "exportar"
    IMPORTAR_CONTORNOS = "importar_contornos"


# Menor = antes: zip -> cadastro do monitor (talhões) -> .jdl (já localiza por GPS).
PRIORIDADE: dict[TipoJob, int] = {
    TipoJob.EXPANDIR_ZIP: 50,
    TipoJob.IMPORTAR_GEN4: 60,
    TipoJob.IMPORTAR_CONTORNOS: 60,
    TipoJob.PROCESSAR_ARQUIVO: 100,
    TipoJob.EXPORTAR: 120,
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
    CONTORNO = "contorno"  # shapefile do talhão (ex.: OMNI): perímetro, cabeceira, linhas-guia
    RCD = "rcd"  # GreenStar 3: par .fdl + .fdd de uma operação (empacotado na expansão do zip)
    ISOXML = "isoxml"  # ISOBUS: TASKDATA.XML + um TLG (.XML/.BIN), de qualquer marca


_EXTENSOES = {".jdl": TipoArquivo.JDL, ".zip": TipoArquivo.ZIP, ".gjson": TipoArquivo.GJSON}

# Arquivos do OMNI por talhão: o .prj vai no payload; .shp e .dbf ficam guardados.
SHAPEFILES_TALHAO = frozenset(
    {
        "_perimeter.shp",
        "_perimeter.prj",
        "_headland.shp",
        "_headland.dbf",
        "_runline.shp",
        "_runline.dbf",
    }
)


def tipo_do_arquivo(nome: str) -> TipoArquivo | None:
    """Pelo nome (o conteúdo é validado depois pelo adapter)."""
    base = posixpath.basename(nome.replace("\\", "/"))
    if base.lower() == "masterdata.xml":
        return TipoArquivo.MASTERDATA
    if base.lower() in SHAPEFILES_TALHAO:  # OMNI: Data/<cliente>/<talhão>/
        return TipoArquivo.CONTORNO
    _, ext = posixpath.splitext(base.lower())
    if ext in (".fdl", ".fdd"):  # GS3: RCD/EIC/Documentation/<xx>/<uuid>.fd?
        return TipoArquivo.RCD
    if base.lower() == "taskdata.xml" or _TLG.fullmatch(base.lower()):
        return TipoArquivo.ISOXML
    return _EXTENSOES.get(ext)


_MAGICO_RCD = b"SERRANO-RCD1\n"
_MAGICO_ISOXML = b"SERRANO-ISOXML1\n"
_TLG = re.compile(r"tlg\d{5}\.(xml|bin)")


def empacotar_isoxml(nome_tlg: str, taskdata: bytes, cabecalho: bytes, binario: bytes) -> bytes:
    """Um TLG com o TASKDATA.XML da mesma pasta (é ele que diz talhão, cliente e máquina)."""
    nome = nome_tlg.encode()
    return (
        _MAGICO_ISOXML
        + len(nome).to_bytes(2, "little")
        + nome
        + len(taskdata).to_bytes(4, "little")
        + taskdata
        + len(cabecalho).to_bytes(4, "little")
        + cabecalho
        + binario
    )


def eh_pacote_isoxml(cabeca: bytes) -> bool:
    return cabeca.startswith(_MAGICO_ISOXML)


def desempacotar_isoxml(pacote: bytes) -> tuple[str, bytes, bytes, bytes]:
    """-> (nome do TLG, TASKDATA.XML, TLG.XML, TLG.BIN)."""
    if not eh_pacote_isoxml(pacote):
        raise ValueError("pacote ISOXML inválido")
    i = len(_MAGICO_ISOXML)
    partes: list[bytes] = []
    n = int.from_bytes(pacote[i : i + 2], "little")
    partes.append(pacote[i + 2 : i + 2 + n])
    i += 2 + n
    for _ in range(2):
        n = int.from_bytes(pacote[i : i + 4], "little")
        if i + 4 + n > len(pacote):
            raise ValueError("pacote ISOXML truncado")
        partes.append(pacote[i + 4 : i + 4 + n])
        i += 4 + n
    return partes[0].decode(), partes[1], partes[2], pacote[i:]


def empacotar_rcd(fdl: bytes, fdd: bytes) -> bytes:
    """Um arquivo só para o par do GreenStar 3: o .fdl dá o significado do .fdd."""
    return _MAGICO_RCD + len(fdl).to_bytes(4, "little") + fdl + fdd


def eh_pacote_rcd(cabeca: bytes) -> bool:
    return cabeca.startswith(_MAGICO_RCD)


def desempacotar_rcd(pacote: bytes) -> tuple[bytes, bytes]:
    if not eh_pacote_rcd(pacote) or len(pacote) < len(_MAGICO_RCD) + 4:
        raise ValueError("pacote GS3 inválido")
    i = len(_MAGICO_RCD)
    n = int.from_bytes(pacote[i : i + 4], "little")
    if i + 4 + n > len(pacote):
        raise ValueError("pacote GS3 truncado")
    return pacote[i + 4 : i + 4 + n], pacote[i + 4 + n :]


_INSEGURO = re.compile(r"[^\w.\-\[\]{}() ,]+", re.UNICODE)


def nome_para_exibicao(nome: str) -> str:
    """Nome do cliente só para exibição: sem diretórios nem caracteres de controle."""
    base = posixpath.basename(nome.replace("\\", "/")).strip()
    return (_INSEGURO.sub("_", base) or "arquivo")[:200]


def caminho_bruto(organizacao_id: UUID, sha256: str, tipo: TipoArquivo) -> str:
    """O nome do cliente nunca vira caminho: brutos/<org>/<sha256>.<ext>."""
    ext = {TipoArquivo.MASTERDATA: "xml", TipoArquivo.CONTORNO: "shp"}.get(tipo, tipo.value)
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
