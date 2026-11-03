"""Telemetria em janelas: menos linhas, mesmos segundos, litros e distância."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sistemacampero.infrastructure.persistence.resultados import COLUNAS_TELEMETRIA, compactar


def _limpo(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    ts = pd.date_range("2026-05-20 12:00:00", periods=n, freq="1s", tz="UTC")
    vel = np.where(np.arange(n) % 300 < 240, 6 + rng.normal(0, 0.3, n), 0.2)  # trabalha e para
    df = pd.DataFrame(dict.fromkeys(COLUNAS_TELEMETRIA, np.nan), index=range(n))
    df["ts"] = ts
    df["lat"], df["lon"] = -28.1 + np.arange(n) * 1e-6, -52.9
    df["gps_valid"] = True
    df["speed_kmh"] = vel
    df["fuel_rate_lph"] = np.where(vel >= 1, 25.0, 3.0)
    df.loc[100:109, "fuel_rate_lph"] = np.nan  # buraco de sensor
    df["engine_on"] = np.arange(n) < n - 60  # desliga no fim
    df["engine_hours"] = 1000 + np.arange(n) / 3600
    return df


def test_janelas_preservam_totais() -> None:
    limpo = _limpo(3600)
    j = compactar(limpo, [None] * len(limpo))
    assert len(j) < len(limpo) / 8  # ~10 s por linha
    assert j["peso_s"].sum() == len(limpo)

    def totais(df: pd.DataFrame, peso: pd.Series) -> tuple[float, float, float, float]:
        lig = df["engine_on"].astype(bool)
        trab = lig & (df["speed_kmh"] >= 1)
        return (
            float(peso[lig].sum()),
            float(peso[trab].sum()),
            float((df["fuel_rate_lph"].fillna(0) * peso)[lig].sum() / 3600),
            float((df["speed_kmh"] * peso)[trab].sum() / 3600),
        )

    esperado = totais(limpo, pd.Series(1, index=limpo.index))
    obtido = totais(j, j["peso_s"])
    assert obtido == pytest.approx(esperado, rel=1e-9)
    assert j["engine_hours"].iloc[-1] == limpo["engine_hours"].iloc[-1]


def test_janela_nao_mistura_talhoes() -> None:
    limpo = _limpo(20)
    talhoes = ["a"] * 5 + ["b"] * 15
    j = compactar(limpo, talhoes)
    assert list(j["talhao_id"]) == ["a", "b", "b"]
    assert list(j["peso_s"]) == [5, 5, 10]
