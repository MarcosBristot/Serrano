"""Redução de resolução das amostras (1 Hz -> N s) para persistência no banco."""

from __future__ import annotations

import pandas as pd

_COUNTERS = ("fuel_total_l", "engine_hours")
_FLAGS = ("gps_valid", "engine_on")


def decimate(samples: pd.DataFrame, step_s: int) -> pd.DataFrame:
    """Agrega amostras em janelas de ``step_s`` segundos.

    Grandezas instantâneas usam média, contadores usam o último valor da janela e
    indicadores booleanos usam ``any``. ``step_s <= 1`` devolve o dado original.
    """
    if step_s <= 1 or samples.empty:
        return samples.reset_index(drop=True)
    bucket = pd.Series(range(len(samples))) // step_s
    grouped = samples.reset_index(drop=True).groupby(bucket)
    agg: dict[str, str] = {}
    for col in samples.columns:
        if col == "ts" or col in _COUNTERS:
            agg[col] = "first" if col == "ts" else "last"
        elif col in _FLAGS:
            agg[col] = "max"
        else:
            agg[col] = "mean"
    out = grouped.agg(agg).reset_index(drop=True)
    for col in _FLAGS:
        out[col] = out[col].astype(bool)
    return out
