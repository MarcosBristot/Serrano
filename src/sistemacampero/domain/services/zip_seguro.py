"""Expansão segura de .zip do pendrive (contra zip slip e zip bomb).

Só devolve conteúdo e nome de EXIBIÇÃO: o nome nunca vira caminho em disco
(o Storage usa o sha256). Limites: tamanho descompactado total e por entrada,
número de entradas e taxa de compressão por entrada.
"""

from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.ingestao import TipoArquivo, nome_para_exibicao, tipo_do_arquivo


@dataclass(frozen=True)
class LimitesZip:
    max_entradas: int = 10_000
    max_total_bytes: int = 4 * 1024**3
    max_entrada_bytes: int = 512 * 1024**2
    max_taxa_compressao: float = 200.0  # .jdl comprime ~5-20x; 1000x é bomba


@dataclass(frozen=True, slots=True)
class EntradaZip:
    nome: str  # para exibição
    caminho_no_zip: str
    tipo: TipoArquivo
    conteudo: bytes


def _caminho_seguro(nome: str) -> bool:
    n = nome.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        return False
    return ".." not in posixpath.normpath(n).split("/")


def expandir(dados: BinaryIO, limites: LimitesZip | None = None) -> Iterator[EntradaZip]:
    """Itera as entradas úteis (.jdl, MasterData.xml, .gjson); ignora o resto."""
    lim = limites or LimitesZip()
    try:
        zf = zipfile.ZipFile(dados)
    except zipfile.BadZipFile as exc:
        raise Invalido("Arquivo .zip corrompido.", codigo="ZIP_INVALIDO") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > lim.max_entradas:
            raise Invalido(
                f"O .zip tem {len(infos)} entradas (máximo {lim.max_entradas}).",
                codigo="ZIP_GRANDE_DEMAIS",
            )
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            if not _caminho_seguro(info.filename):
                raise Invalido(
                    "O .zip contém caminho perigoso (fora da pasta).", codigo="ZIP_CAMINHO_INSEGURO"
                )
            tipo = tipo_do_arquivo(info.filename)
            if tipo is None or tipo is TipoArquivo.ZIP:
                continue  # zip dentro de zip não é expandido
            if info.file_size > lim.max_entrada_bytes:
                raise Invalido(
                    f"Entrada grande demais no .zip: {nome_para_exibicao(info.filename)}.",
                    codigo="ZIP_GRANDE_DEMAIS",
                )
            if info.compress_size and info.file_size / info.compress_size > lim.max_taxa_compressao:
                raise Invalido("Taxa de compressão suspeita (zip bomb).", codigo="ZIP_BOMBA")
            total += info.file_size
            if total > lim.max_total_bytes:
                raise Invalido("O .zip descompactado passa do limite.", codigo="ZIP_GRANDE_DEMAIS")
            # O tamanho declarado pode mentir: lê com teto.
            with zf.open(info) as fh:
                conteudo = fh.read(lim.max_entrada_bytes + 1)
            if len(conteudo) > lim.max_entrada_bytes:
                raise Invalido("Entrada maior que o declarado (zip bomb).", codigo="ZIP_BOMBA")
            yield EntradaZip(nome_para_exibicao(info.filename), info.filename, tipo, conteudo)
