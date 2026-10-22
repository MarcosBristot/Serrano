"""Schema universal de telemetria e contrato de saída dos adapters de fabricante.

Convenções (contrato entre marcas, verificado em ``tests/contrato``):

* uma linha por segundo (1 Hz), ``ts`` em UTC, estritamente crescente;
* unidades métricas: km/h, L, L/h, h, graus decimais WGS84;
* ausência = ``NaN`` (nunca 0). Ex.: o John Deere Gen4 não informa nível de tanque,
  então ``fuel_level_l`` é sempre ``NaN``;
* ``engine_on`` sai do adapter como ``<NA>`` quando o fabricante não informa o estado
  do motor; a sanitização deriva o valor cruzando RPM, vazão e horímetro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from sistemacampero.domain.errors import Invalido

#: Colunas do DataFrame de amostras (ordem = ordem de persistência). Os nomes das medidas
#: são um contrato entre adapters, por isso ficam em inglês também no banco.
COLUNAS_UNIVERSAIS: dict[str, str] = {
    "ts": "datetime64[ns, UTC]",
    "lat": "float64",
    "lon": "float64",
    "gps_valid": "bool",  # há posição de GPS neste segundo
    "speed_kmh": "float64",  # velocidade (roda/radar)
    "speed_alt_kmh": "float64",  # segundo sensor de velocidade
    "engine_rpm": "float64",
    "engine_load_pct": "float64",
    "fuel_rate_lph": "float64",  # vazão instantânea
    "fuel_total_l": "float64",  # contador acumulado do motor
    "fuel_level_l": "float64",  # nível do tanque
    "engine_hours": "float64",  # horímetro acumulado
    "engine_on": "boolean",  # <NA> = não informado pelo fabricante
}

MEDIDAS = tuple(c for c in COLUNAS_UNIVERSAIS if c not in ("ts", "lat", "lon", "gps_valid"))


def amostras_vazias() -> pd.DataFrame:
    """DataFrame vazio no schema universal."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in COLUNAS_UNIVERSAIS.items()})


def no_schema_universal(df: pd.DataFrame) -> pd.DataFrame:
    """Reordena e converte os tipos; colunas que faltam entram como ausentes."""
    out = pd.DataFrame(index=df.index)
    for col, tipo in COLUNAS_UNIVERSAIS.items():
        if col in df:
            out[col] = df[col]
        elif tipo == "bool":
            out[col] = False
        elif tipo == "boolean":
            out[col] = pd.array([pd.NA] * len(df), dtype="boolean")
        else:
            out[col] = float("nan")
    return out.astype(COLUNAS_UNIVERSAIS).reset_index(drop=True)


def normalizar_guid(guid: str | None) -> str | None:
    """'{AAB549AD-...}' -> 'aab549ad-...' (o .jdl e o MasterData.xml escrevem diferente)."""
    if not guid:
        return None
    limpo = guid.strip().strip("{}").strip().lower()
    return limpo or None


class ArquivoInvalido(Invalido):
    """O arquivo não está no formato que o adapter declara ler."""

    codigo = "ARQUIVO_INVALIDO"


@dataclass(frozen=True, slots=True)
class ParseContext:
    """O que se sabe do arquivo antes de lê-lo (vem do upload)."""

    nome_arquivo: str
    marca: str | None = None
    tecnologia: str | None = None


@dataclass(frozen=True, slots=True)
class MetadadosSessao:
    fabricante: str
    serial_maquina: str | None
    inicio: datetime
    fim: datetime
    modelo: str | None = None
    serial_monitor: str | None = None
    firmware: str | None = None
    cliente_nome: str | None = None
    cliente_guid: str | None = None
    fazenda_nome: str | None = None
    fazenda_guid: str | None = None
    talhao_nome: str | None = None
    talhao_guid: str | None = None
    implemento_nome: str | None = None
    implemento_largura_m: float | None = None
    operacao: str | None = None


@dataclass(slots=True)
class Diagnostico:
    """Como o arquivo foi lido: canais usados, escalas, descartes e avisos (auditoria)."""

    canais: dict[str, dict[str, Any]] = field(default_factory=dict)  # coluna -> origem
    canais_ausentes: list[str] = field(default_factory=list)
    fonte_posicao: str = "nenhuma"  # trilha_gps | caixa_do_bloco | nenhuma
    contadores: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedSession:
    """Sessão de trabalho (um arquivo do monitor) no schema universal."""

    sha256: str
    adapter: str
    adapter_versao: str
    metadados: MetadadosSessao
    amostras: pd.DataFrame
    diagnostico: Diagnostico


@dataclass(frozen=True, slots=True)
class EmptyFile:
    """Arquivo válido, mas sem amostras (ex.: só cabeçalho). Não é erro."""

    sha256: str
    adapter: str
    adapter_versao: str
    motivo: str  # sem_blocos_de_dados | sem_canais_do_trator | sem_horario_de_inicio
    explicacao: str
    serial_maquina: str | None = None
