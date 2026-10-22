from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from sistemacampero.domain.services.kpis import Somas, derivar, intervalo_da_safra, safra
from sistemacampero.domain.services.mapas import mapa_de_calor, trajeto


def test_razoes_sem_base_sao_none_e_nunca_infinito() -> None:
    i = derivar(Somas())
    assert (i.l_ha, i.ha_h, i.ociosidade_pct, i.rs_ha, i.lph_trabalho) == (
        None,
        None,
        None,
        None,
        None,
    )
    i = derivar(
        Somas(
            motor_h=10,
            trabalho_h=8,
            ocioso_h=2,
            litros=200,
            litros_trabalho=180,
            litros_ocioso=20,
            area_ha=40,
            custo_rs=1318.0,
        )
    )
    assert i.ociosidade_pct == pytest.approx(20)
    assert i.l_ha == pytest.approx(5) and i.ha_h == pytest.approx(5)
    assert i.lph_trabalho == pytest.approx(22.5) and i.lph_ocioso == pytest.approx(10)
    assert i.rs_ha == pytest.approx(32.95) and i.rs_h == pytest.approx(131.8)
    assert i.custo_ocioso_rs == pytest.approx(20 * 6.59)


@pytest.mark.parametrize(
    ("dia", "esperado"),
    [(date(2026, 4, 30), "2025/26"), (date(2026, 7, 1), "2026/27"), (date(2027, 3, 10), "2026/27")],
)
def test_safra_comeca_em_julho(dia: date, esperado: str) -> None:
    assert safra(dia) == esperado
    assert intervalo_da_safra(esperado)[0] <= dia < intervalo_da_safra(esperado)[1]


def test_safra_com_outro_mes_de_inicio() -> None:
    assert safra(date(2026, 8, 1), inicio_safra_mes=9) == "2025/26"
    with pytest.raises(ValueError):
        intervalo_da_safra("vinte e seis")


def _pontos(n: int = 1200, parada: tuple[int, int] | None = (400, 600)) -> pd.DataFrame:
    ts = pd.date_range("2026-04-30 10:00", periods=n, freq="s", tz="UTC")
    vel = np.full(n, 8.0)
    if parada:
        vel[parada[0] : parada[1]] = 0.0
    passo = np.cumsum(vel / 3.6) / 111_320
    return pd.DataFrame(
        {
            "ts": ts,
            "lat": -28.10 + passo,
            "lon": -52.92 + 0.0001 * np.sin(np.arange(n) / 30),
            "speed_kmh": vel,
            "engine_on": True,
        }
    )


def test_trajeto_separa_trabalho_e_parada_e_respeita_max_pontos() -> None:
    fc = trajeto(_pontos(), max_pontos=150)
    tipos = [f["properties"]["tipo"] for f in fc["features"]]
    assert tipos.count("trabalho") == 2 and "parada" in tipos
    parada = next(f for f in fc["features"] if f["properties"]["tipo"] == "parada")
    assert parada["properties"]["minutos"] == pytest.approx(3.3, abs=0.1)
    assert parada["properties"]["motor_ligado"] is True
    vertices = sum(
        len(f["geometry"]["coordinates"])
        for f in fc["features"]
        if f["geometry"]["type"] == "LineString"
    )
    assert vertices <= 150
    # Contínuo: um trecho começa onde o anterior terminou.
    linhas = [f for f in fc["features"] if f["geometry"]["type"] == "LineString"]
    for a, b in zip(linhas, linhas[1:], strict=False):
        assert a["geometry"]["coordinates"][-1] == b["geometry"]["coordinates"][0]


def test_trajeto_vazio() -> None:
    assert trajeto(_pontos().assign(lat=np.nan))["features"] == []


def test_mapa_de_calor_conserva_litros_e_da_l_ha_coerente() -> None:
    df = _pontos(parada=None).assign(fuel_rate_lph=22.0, largura_m=4.95)
    fc = mapa_de_calor(df, tamanho_m=50, area_minima_ha=0)
    total_litros = sum(f["properties"]["litros"] for f in fc["features"])
    assert total_litros == pytest.approx(22.0 * 1200 / 3600, rel=0.01)
    # 22 L/h a 8 km/h com 4,95 m: 22 / (8 x 4,95 / 10) = 5,56 L/ha em todo hexágono.
    assert fc["properties"]["l_ha_p50"] == pytest.approx(5.56, abs=0.02)
    hexagono = fc["features"][0]["geometry"]["coordinates"][0]
    assert len(hexagono) == 7 and hexagono[0] == hexagono[-1]


def test_mapa_de_calor_ignora_parado_e_sem_largura() -> None:
    df = _pontos(parada=None).assign(fuel_rate_lph=22.0, largura_m=np.nan)
    assert mapa_de_calor(df)["features"] == []
    assert mapa_de_calor(df.assign(largura_m=5.0, speed_kmh=0.0))["features"] == []
