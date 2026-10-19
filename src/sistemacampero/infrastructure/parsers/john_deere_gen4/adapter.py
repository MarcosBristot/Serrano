"""Adapter John Deere Gen4: .jdl -> WorkSession (schema universal, 1 Hz)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from sistemacampero.domain.entities import (
    ENGINE_ON_RPM,
    SAMPLE_COLUMNS,
    ContextInfo,
    MachineInfo,
    WorkSession,
    empty_samples,
)
from sistemacampero.infrastructure.parsers.john_deere_gen4 import channels as ch
from sistemacampero.infrastructure.parsers.john_deere_gen4.jdl import (
    ChannelDef,
    JdlFile,
    JdlFormatError,
    read_jdl,
)

ADAPTER_NAME = "john_deere_gen4"
ADAPTER_VERSION = "0.1.0"
MAX_FILL_S = 5  # preenche no máximo 5 s de buraco em grandezas instantâneas


def _wanted(c: ChannelDef) -> bool:
    m = ch.DDI_TO_COLUMN.get(c.ddi)
    return bool(m) and c.group in ch.TRACTOR_GROUPS and c.unit == m[1]


def _valid_gps(p) -> bool:
    return (
        p is not None
        and -90 <= p[0] <= 90
        and -180 <= p[1] <= 180
        and (abs(p[0]) > 1e-6 or abs(p[1]) > 1e-6)
    )


class JohnDeereGen4Adapter:
    """Adapter do monitor John Deere Gen4 (arquivos ``.jdl``)."""

    name = ADAPTER_NAME
    version = ADAPTER_VERSION
    manufacturer = "John Deere"
    technology = "Gen4"

    def can_parse(self, path: Path) -> bool:
        path = Path(path)
        if path.suffix.lower() != ".jdl":
            return False
        with path.open("rb") as fh:
            head = fh.read(5)
        return len(head) == 5 and head[0] == 0x0D

    # ------------------------------------------------------------------ parse
    def parse(self, path: Path) -> WorkSession:
        path = Path(path)
        jdl = read_jdl(path, channel_filter=_wanted)
        warnings: list[str] = []
        if jdl.started_at_ms is None:
            raise JdlFormatError("cabeçalho sem horário de início")
        t0 = pd.Timestamp(jdl.started_at_ms, unit="ms", tz="UTC")

        columns = self._series_to_columns(jdl, warnings)
        samples = self._resample(columns, jdl, t0, warnings)

        impl = jdl.implements[0] if jdl.implements else None
        context = ContextInfo(
            client_name=jdl.client_name,
            farm_name=jdl.farm_name,
            field_guid=jdl.field_guid,
            field_name=jdl.field_name,
            implement_name=impl.name if impl else None,
            implement_width_m=impl.width_m if impl else None,
            operation="plantio" if "Plantio" in jdl.device_names else None,
        )
        machine = MachineInfo(
            manufacturer="John Deere",
            serial=jdl.machine_serial or "desconhecido",
            display_serial=jdl.display_serial,
        )
        chunk_list = [(c.duration_ms, c.start, c.end) for c in jdl.chunks]
        return WorkSession(
            source_file=path.name,
            source_sha256=jdl.sha256,
            adapter=ADAPTER_NAME,
            adapter_version=ADAPTER_VERSION,
            machine=machine,
            context=context,
            started_at=t0.to_pydatetime(),
            samples=samples,
            gps_chunks=chunk_list,
            warnings=warnings,
        )

    # --------------------------------------------------------------- internals
    @staticmethod
    def _series_to_columns(jdl: JdlFile, warnings: list[str]) -> dict[str, tuple]:
        """Converte séries brutas em (t_ms, valores físicos), tratando 'não disponível'."""
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for cid, s in jdl.series.items():
            c = jdl.channels[cid]
            col = ch.DDI_TO_COLUMN[c.ddi][0]
            raw = np.asarray(s.raw, dtype=np.int64)
            t = np.asarray(s.t_ms, dtype=np.float64)
            vals = raw / c.scale + c.offset
            vals[raw <= ch.RAW_NA] = np.nan
            if col in out and len(t) <= len(out[col][0]):
                continue  # canal duplicado: mantém o que tem mais amostras
            out[col] = (t, vals)
        missing = [c for c, _ in ch.DDI_TO_COLUMN.values() if c not in out]
        if missing and jdl.series:
            warnings.append(f"canais ausentes no arquivo: {sorted(set(missing))}")
        return out

    def _resample(self, columns, jdl: JdlFile, t0, warnings) -> pd.DataFrame:
        if not columns:
            return empty_samples()
        horizon_ms = max(t[-1] for t, _ in columns.values() if len(t))
        n = int(math.ceil(horizon_ms / 1000.0)) + 1
        grid = pd.DataFrame(index=np.arange(n))

        for col, (t, v) in columns.items():
            if not len(t):
                continue
            bins = np.floor(t / 1000.0).astype(np.int64)
            ser = pd.Series(v, index=bins)
            if col in ch.COUNTER_COLUMNS:
                agg = ser.groupby(level=0).last()
                grid[col] = agg.reindex(grid.index).ffill()
            else:
                agg = ser.groupby(level=0).mean()
                grid[col] = agg.reindex(grid.index).ffill(limit=MAX_FILL_S)

        # posição: pontos de início/fim de blocos de ~30 s, interpolados a 1 Hz
        lat = np.full(n, np.nan)
        lon = np.full(n, np.nan)
        gps_ok = np.zeros(n, dtype=bool)
        clock = 0.0
        for chunk in jdl.chunks:
            a, b = chunk.start, chunk.end
            if _valid_gps(a) and _valid_gps(b):
                i0 = int(clock // 1000)
                i1 = min(int((clock + chunk.duration_ms) // 1000), n - 1)
                if i1 >= i0:
                    k = np.arange(i0, i1 + 1)
                    frac = np.clip((k * 1000.0 - clock) / max(chunk.duration_ms, 1), 0, 1)
                    lat[k] = a[0] + (b[0] - a[0]) * frac
                    lon[k] = a[1] + (b[1] - a[1]) * frac
                    gps_ok[k] = True
            clock += chunk.duration_ms

        df = pd.DataFrame(index=grid.index)
        df["ts"] = t0 + pd.to_timedelta(grid.index, unit="s")
        df["lat"], df["lon"], df["gps_valid"] = lat, lon, gps_ok
        for col in SAMPLE_COLUMNS:
            if col in ("ts", "lat", "lon", "gps_valid", "engine_on"):
                continue
            df[col] = grid.get(col, np.nan)
        df["engine_on"] = (df["engine_rpm"] > ENGINE_ON_RPM).fillna(False)
        df = df[list(SAMPLE_COLUMNS)].reset_index(drop=True)
        return df.astype({k: v for k, v in SAMPLE_COLUMNS.items() if k != "ts"})
