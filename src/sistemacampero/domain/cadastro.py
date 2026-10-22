"""Cadastro: fazendas, talhões, máquinas, implementos e operadores."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from shapely.geometry import MultiPolygon


class OrigemContorno(StrEnum):
    MONITOR = "monitor"  # importado do Gen4 (MasterData + SpatialFiles)
    UPLOAD = "upload"  # .gjson/GeoJSON enviado pelo gestor
    DESENHO = "desenho"  # desenhado no mapa do frontend


class OrigemTalhao(StrEnum):
    GPS = "gps"  # maioria dos pontos de trabalho dentro do contorno
    MONITOR = "monitor"  # talhão selecionado no monitor (cabeçalho do .jdl)
    MANUAL = "manual"  # correção do gestor: nunca é sobrescrita
    NENHUM = "nenhum"


@dataclass(frozen=True, slots=True)
class FazendaImportada:
    guid: str
    nome: str
    cliente_nome: str | None = None


@dataclass(frozen=True, slots=True)
class TalhaoImportado:
    guid: str
    nome: str
    fazenda_guid: str | None
    contorno: MultiPolygon | None


@dataclass(frozen=True, slots=True)
class ImplementoImportado:
    guid: str
    nome: str
    largura_m: float | None


@dataclass(frozen=True, slots=True)
class OperadorImportado:
    guid: str
    nome: str


@dataclass(slots=True)
class ImportacaoCadastro:
    fazendas: list[FazendaImportada] = field(default_factory=list)
    talhoes: list[TalhaoImportado] = field(default_factory=list)
    implementos: list[ImplementoImportado] = field(default_factory=list)
    operadores: list[OperadorImportado] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResumoImportacao:
    fazendas: int
    talhoes: int
    contornos_novos: int  # talhões que ganharam/mudaram contorno (=> relocalizar sessões)
    contornos_preservados: int  # contorno do gestor (upload/desenho) não é sobrescrito
    implementos: int
    operadores: int
