import numpy as np
import pandas as pd

from sistemacampero.domain.entities import FieldBoundary
from sistemacampero.domain.services.decimation import decimate
from sistemacampero.domain.services.geo import FieldLocator
from tests.conftest import FIELD_GEOJSON


def _field(fid="a", geometry=FIELD_GEOJSON):
    return FieldBoundary(id=fid, name=f"Talhao {fid}", geometry=geometry)


def test_locator_associa_ponto_ao_talhao_e_ignora_fora_e_nan():
    locator = FieldLocator([_field()])
    idx = locator.locate(np.array([-28.08, -29.0, np.nan]), np.array([-52.92, -52.92, -52.92]))
    assert idx.tolist() == [0, -1, -1]
    assert locator.field_ids(np.array([-28.08]), np.array([-52.92])) == ["a"]


def test_locator_sem_talhoes_devolve_fora():
    assert FieldLocator([]).locate(np.array([-28.0]), np.array([-52.0])).tolist() == [-1]


def test_talhao_dominante_da_sessao():
    df = pd.DataFrame({"lat": [-28.08] * 8 + [-29.0] * 2, "lon": [-52.92] * 10})
    assert FieldLocator([_field()]).dominant_field(df).id == "a"
    assert FieldLocator([_field()]).dominant_field(df.assign(lat=-29.0)) is None


def test_decimacao_media_ultimo_e_flags():
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=10, freq="s", tz="UTC"),
            "lat": np.nan,
            "lon": np.nan,
            "gps_valid": False,
            "speed_kmh": np.arange(10.0),
            "speed_alt_kmh": np.nan,
            "engine_rpm": 1800.0,
            "engine_load_pct": np.nan,
            "fuel_rate_lph": 20.0,
            "fuel_total_l": np.arange(100.0, 110.0),
            "fuel_level_l": np.nan,
            "engine_hours": 1.0,
            "engine_on": [False] * 4 + [True] * 6,
        }
    )
    out = decimate(df, 5)
    assert len(out) == 2
    assert out["speed_kmh"].tolist() == [2.0, 7.0]
    assert out["fuel_total_l"].tolist() == [104.0, 109.0]
    assert out["engine_on"].tolist() == [True, True]
    assert len(decimate(df, 1)) == 10
