import math
from pathlib import Path

import numpy as np
import pytest

from sistemacampero.adapters.john_deere_gen4 import JohnDeereGen4Adapter
from sistemacampero.adapters.john_deere_gen4.jdl import JdlFormatError, read_jdl
from sistemacampero.analytics.rules import RuleConfig, detect_counter_mismatch, detect_idle
from sistemacampero.processing.clean import sanitize
from sistemacampero.processing.metrics import compute_session_metrics
from tests.jdl_builder import build_jdl


@pytest.fixture
def work_file(tmp_path) -> Path:
    p = tmp_path / "trabalho.jdl"
    p.write_bytes(build_jdl(speed_kmh=8.0, fuel_lph=22.0, rpm=1800, minutes=30))
    return p


def test_decodifica_valores_fisicos(work_file):
    jdl = read_jdl(work_file)
    assert jdl.software_version == "10.30.0-test"
    assert (jdl.client_name, jdl.field_name) == ("Cliente Teste", "Talhao Teste")
    assert jdl.implements[0].width_m == pytest.approx(4.95)
    s = jdl.series[1]
    assert s.raw[-1] / 1000 == pytest.approx(8.0)
    assert len(s.raw) == 30 * 2 * 150
    assert s.t_ms[-1] / 1000 == pytest.approx(30 * 60, rel=0.01)  # dt em 0,5 ms


def test_adapter_schema_e_unidades(work_file):
    sess = JohnDeereGen4Adapter().parse(work_file)
    df = sess.samples
    assert len(df) == pytest.approx(1800, abs=2)
    assert df["speed_kmh"].median() == pytest.approx(8.0)
    assert df["fuel_rate_lph"].median() == pytest.approx(22.0)
    assert df["engine_rpm"].median() == pytest.approx(1800.0)
    assert df["fuel_level_l"].isna().all()           # JD não informa nível de tanque
    assert df["engine_on"].all() and df["gps_valid"].mean() > 0.95
    assert sess.context.operation is None and sess.context.implement_name == "Plantadeira Teste"


def test_metricas_combustivel_area(work_file):
    sess = JohnDeereGen4Adapter().parse(work_file)
    clean, _ = sanitize(sess.samples)
    m = compute_session_metrics(sess, clean)
    assert m.fuel_integral_l == pytest.approx(22.0 * 0.5, rel=0.03)      # 22 L/h x 30 min
    assert m.work_distance_km == pytest.approx(4.0, rel=0.03)            # 8 km/h x 0,5 h
    assert m.worked_area_ha == pytest.approx(4.0 * 1000 * 4.95 / 1e4, rel=0.03)
    assert m.l_per_ha == pytest.approx(m.fuel_integral_l / m.worked_area_ha)
    assert m.idle_h == 0


def test_sentinela_nao_disponivel_vira_nan(tmp_path):
    # velocidade absurda (> 40 km/h) e RPM fora do limite viram NaN na sanitização
    p = tmp_path / "ruim.jdl"
    p.write_bytes(build_jdl(speed_kmh=95.0, fuel_lph=20.0, rpm=1800, minutes=2))
    sess = JohnDeereGen4Adapter().parse(p)
    clean, q = sanitize(sess.samples)
    assert clean["speed_kmh"].isna().all() and q["speed_kmh_fora_do_limite"] > 0


def test_regra_ociosidade(tmp_path):
    p = tmp_path / "parado.jdl"
    p.write_bytes(build_jdl(speed_kmh=0.0, fuel_lph=3.2, rpm=900, minutes=25, with_gps=False))
    sess = JohnDeereGen4Adapter().parse(p)
    clean, _ = sanitize(sess.samples)
    alerts = detect_idle(sess, clean, RuleConfig())
    assert len(alerts) == 1 and alerts[0].value == pytest.approx(25, abs=1)
    assert alerts[0].details["litros"] == pytest.approx(3.2 * 25 / 60, rel=0.05)


def test_arquivo_truncado_gera_erro_claro(tmp_path):
    p = tmp_path / "x.jdl"
    p.write_bytes(build_jdl(8, 20, 1800, 1)[:-10])
    with pytest.raises(JdlFormatError):
        read_jdl(p)


def test_contador_nan_nao_gera_alerta(work_file):
    # regressão: NaN passava na comparação e gerava alerta "nan%" (238 falsos no dado real)
    sess = JohnDeereGen4Adapter().parse(work_file)
    clean, _ = sanitize(sess.samples)
    m = compute_session_metrics(sess, clean)
    m.fuel_counter_l = float("nan")
    assert detect_counter_mismatch(sess, m, RuleConfig()) == []
    m.fuel_counter_l, m.fuel_integral_l = 100.0, 50.0
    assert len(detect_counter_mismatch(sess, m, RuleConfig())) == 1
