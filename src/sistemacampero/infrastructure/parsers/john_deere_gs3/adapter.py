"""Adapter John Deere GreenStar 3 2630 (colheitadeira): par .fdl + .fdd -> schema universal.

O par chega como um pacote único (``domain.ingestao.empacotar_rcd``), montado na expansão do
.zip do pendrive. Mapeamento validado em 321 operações reais de uma S540 (2022-2026):

* posição: receptor ``GPS*_5140`` (o ``_5141`` é a projeção na plataforma);
* ``speed_kmh`` = ``vrVehicleSpeed``; ``speed_alt_kmh`` = ``vrDistanceTraveled`` (cm) / intervalo;
* ``fuel_rate_lph`` = ``vrFuelRatePerHour``; o monitor não informa motor, RPM nem horímetro
  (``engine_on`` = <NA>, a sanitização deriva pela vazão);
* colheita (``vrYieldWetMass`` em kg por registro e ``vrHarvestMoisture``) ainda não tem coluna no
  schema universal: os totais vão para o diagnóstico.
"""

from __future__ import annotations

import hashlib
from typing import BinaryIO

import numpy as np
import pandas as pd

from sistemacampero.domain.ingestao import desempacotar_rcd, eh_pacote_rcd
from sistemacampero.domain.telemetry import (
    ArquivoInvalido,
    Diagnostico,
    EmptyFile,
    MetadadosSessao,
    ParseContext,
    ParsedSession,
    no_schema_universal,
    normalizar_guid,
)
from sistemacampero.infrastructure.parsers.john_deere_gs3.rcd import (
    Bloco,
    Fdl,
    RcdFormatError,
    ler_fdd,
    ler_fdl,
)

ADAPTER = "john_deere_gs3"
VERSAO = "1.0.0"
MAX_FILL_S = 5  # como no Gen4: preenche no máximo 5 s de buraco

# representação no .fdl -> coluna da tabela intermediária
_CANAIS = {
    "vrVehicleSpeed": "speed_kmh",
    "vrFuelRatePerHour": "fuel_rate_lph",
    "vrDistanceTraveled": "dist_cm",
    "vrYieldWetMass": "massa_kg",
    "vrHarvestMoisture": "umidade_pct",
    "dtHeaderStatus": "plataforma",
}


def _indices(bloco: Bloco, fdl: Fdl) -> dict[str, int]:
    """Coluna intermediária -> índice no bloco (primeira ocorrência; GPS do receptor _5140)."""
    ix: dict[str, int] = {}
    for k, c in enumerate(bloco.colunas):
        rep = fdl.colunas.get(c.nome, "")
        destino = _CANAIS.get(rep)
        if c.nome.startswith("GPSLatitude"):
            destino = "lat"
        elif c.nome.startswith("GPSLongitude"):
            destino = "lon"
        elif c.nome == "ElapsedTime":
            destino = "t_ms"
        if destino and destino not in ix:
            ix[destino] = k
    return ix


class JohnDeereGs3Adapter:
    """Monitor GreenStar 3 2630 (pasta ``GS3_2630/.../RCD/EIC/Documentation``)."""

    brand = "john_deere"
    technology = "gs3"
    version = VERSAO

    def can_parse(self, head: bytes, filename: str) -> bool:
        return eh_pacote_rcd(head)

    def parse(self, data: BinaryIO, ctx: ParseContext) -> ParsedSession | EmptyFile:
        bruto = data.read()
        sha = hashlib.sha256(bruto).hexdigest()
        try:
            xml, binario = desempacotar_rcd(bruto)
            fdl = ler_fdl(xml)
            blocos = ler_fdd(binario)
        except (RcdFormatError, ValueError) as exc:
            raise ArquivoInvalido(f"{ctx.nome_arquivo}: {exc}") from exc

        def vazio(motivo: str, explicacao: str) -> EmptyFile:
            return EmptyFile(sha, ADAPTER, VERSAO, motivo, explicacao, fdl.serial_maquina)

        if not fdl.inicios:
            return vazio("sem_horario_de_inicio", "O .fdl não tem a hora de início da gravação.")
        partes = []
        for n, bloco in enumerate(blocos):
            if not bloco.linhas or n >= len(fdl.inicios):
                continue
            ix = _indices(bloco, fdl)
            if "t_ms" not in ix:
                continue
            m = np.array(
                [[np.nan if v is None else float(v) for v in linha] for linha in bloco.linhas]
            )
            df = pd.DataFrame({nome: m[:, k] for nome, k in ix.items()})
            df["ts"] = pd.Timestamp(fdl.inicios[n]) + pd.to_timedelta(df["t_ms"], unit="ms")
            partes.append(df)
        if not partes:
            return vazio(
                "sem_blocos_de_dados",
                "Só cabeçalho: o monitor abriu a operação e não gravou registros.",
            )
        bruta = pd.concat(partes, ignore_index=True).sort_values("ts", kind="stable")
        diag = Diagnostico(fonte_posicao="trilha_gps")
        amostras = self._por_segundo(bruta, diag)
        self._colheita(bruta, diag)
        meta = MetadadosSessao(
            fabricante="John Deere",
            serial_maquina=fdl.serial_maquina,
            inicio=amostras["ts"].iloc[0].to_pydatetime(),
            fim=amostras["ts"].iloc[-1].to_pydatetime(),
            modelo=fdl.modelo,
            cliente_nome=fdl.cliente[0],
            cliente_guid=normalizar_guid(fdl.cliente[1]),
            fazenda_nome=fdl.fazenda[0],
            fazenda_guid=normalizar_guid(fdl.fazenda[1]),
            talhao_nome=fdl.talhao[0],
            talhao_guid=normalizar_guid(fdl.talhao[1]),
            implemento_nome=fdl.implemento,
            implemento_largura_m=fdl.largura_m,
            operacao="colheita",
        )
        return ParsedSession(sha, ADAPTER, VERSAO, meta, amostras, diag)

    @staticmethod
    def _por_segundo(bruta: pd.DataFrame, diag: Diagnostico) -> pd.DataFrame:
        """Registros de ~1 s (e de evento, menores) -> uma linha por segundo (a última)."""
        df = bruta.copy()
        dt_s = df["t_ms"].diff().where(lambda s: s > 0) / 1000.0
        if "dist_cm" in df:
            df["speed_alt_kmh"] = (df["dist_cm"] / dt_s * 0.036).where(dt_s >= 0.5)
        # O monitor grava a cada 1001-1003 ms: grade exata de 1 s, buracos curtos preenchidos.
        df["ts"] = df["ts"].dt.round("s")
        df = df.drop_duplicates("ts", keep="last").set_index("ts")
        grade = pd.date_range(df.index[0], df.index[-1], freq="1s")
        df = df.reindex(grade).ffill(limit=MAX_FILL_S).rename_axis("ts").reset_index()
        validos = df["lat"].between(-90, 90) & df["lon"].between(-180, 180)
        validos &= (df["lat"].abs() > 1e-6) | (df["lon"].abs() > 1e-6)
        df["gps_valid"] = validos.fillna(False).astype(bool)
        df.loc[~df["gps_valid"], ["lat", "lon"]] = np.nan
        for coluna, origem in (
            ("speed_kmh", "vrVehicleSpeed"),
            ("fuel_rate_lph", "vrFuelRatePerHour"),
            ("speed_alt_kmh", "vrDistanceTraveled / intervalo"),
        ):
            if coluna in df and df[coluna].notna().any():
                diag.canais[coluna] = {"origem": origem}
            else:
                diag.canais_ausentes.append(coluna)
        diag.canais_ausentes += ["engine_rpm", "engine_load_pct", "engine_hours", "fuel_total_l"]
        diag.contadores["registros"] = len(bruta)
        diag.contadores["segundos"] = len(df)
        return no_schema_universal(df)

    @staticmethod
    def _colheita(bruta: pd.DataFrame, diag: Diagnostico) -> None:
        if "massa_kg" not in bruta:
            return
        massa = bruta["massa_kg"].clip(lower=0).fillna(0)
        total = float(massa.sum())
        diag.contadores["massa_umida_kg"] = round(total)
        if "umidade_pct" in bruta and total > 0:
            umidade = float((bruta["umidade_pct"].fillna(0) * massa).sum() / total)
            diag.canais["colheita"] = {
                "massa_umida_kg": round(total, 1),
                "umidade_media_pct": round(umidade, 2),
            }
