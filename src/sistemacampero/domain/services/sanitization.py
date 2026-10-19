"""Etapa 2 do pipeline: sanitização do dado já no schema universal.

Nunca altera o arquivo bruto. Valores fisicamente impossíveis viram NaN e são contados
em ``quality`` (que também é persistido, para auditoria).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# limites físicos plausíveis para um trator agrícola
LIMITS: dict[str, tuple[float, float]] = {
    "speed_kmh": (0.0, 40.0),
    "speed_alt_kmh": (0.0, 40.0),
    "engine_rpm": (0.0, 3500.0),
    "engine_load_pct": (0.0, 125.0),
    "fuel_rate_lph": (0.0, 90.0),
}
MONOTONIC = ("engine_hours", "fuel_total_l")
CLEAN_VERSION = "2"  # v2: contadores iguais a 0 (ainda não reportados) viram NaN


def sanitize(samples: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    df = samples.copy()
    quality: dict[str, int] = {}

    for col, (lo, hi) in LIMITS.items():
        bad = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        quality[f"{col}_fora_do_limite"] = int(bad.sum())
        df.loc[bad, col] = np.nan

    for col in MONOTONIC:
        unset = df[col].notna() & (df[col] <= 0)
        quality[f"{col}_zerado_nao_reportado"] = int(unset.sum())
        df.loc[unset, col] = np.nan
        # contador acumulado não pode diminuir: queda = reset/ruído -> invalida o ponto
        cummax = df[col].cummax()
        bad = df[col].notna() & (df[col] < cummax - 1e-9)
        quality[f"{col}_nao_monotonico"] = int(bad.sum())
        df.loc[bad, col] = np.nan
        df[col] = df[col].ffill()

    quality["amostras"] = int(len(df))
    quality["amostras_com_gps"] = int(df["gps_valid"].sum())
    quality["amostras_motor_ligado"] = int(df["engine_on"].sum())
    return df, quality
