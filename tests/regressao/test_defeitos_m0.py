"""Regressão dos 3 defeitos encontrados no código de referência (plano M0, seção 0.2).

Cada caso reproduz, com dado sintético, o que aconteceu no dump real de 2026.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd
import pytest

from sistemacampero.application.processamento import ProcessadorDeArquivo, ResultadoSessao
from sistemacampero.domain.services import rules
from sistemacampero.domain.services.metrics import calcular_metricas
from sistemacampero.domain.services.quality import avaliar
from sistemacampero.domain.services.sanitization import sanitizar
from sistemacampero.domain.telemetry import ParseContext
from sistemacampero.infrastructure.parsers.john_deere_gen4 import JohnDeereGen4Adapter
from sistemacampero.infrastructure.parsers.registry import registro_padrao
from tests.sinteticos.jdl_builder import Cenario, construir


def _processar(c: Cenario) -> ResultadoSessao:
    r = ProcessadorDeArquivo(registro_padrao()).processar(construir(c), ParseContext("s.jdl"))
    assert isinstance(r, ResultadoSessao)
    return r


# ----------------------------------------------------------------- defeito 1
def test_d1_primeiro_bloco_com_valor_acumulado_nao_desloca_a_serie() -> None:
    """106a770c: 8,9 h de dado, mas RPM <= 709 e velocidade <= 4 km/h -> 0,29 h de motor.

    Causa: o 1º bloco já trazia a âncora (valor acumulado) e o leitor somava a partir de 0.
    """
    r = _processar(Cenario(minutos=60, ancora_inicial=True, rpm=lambda _t: 1650.0))
    m = r.metricas
    assert m is not None
    assert r.limpo["engine_rpm"].median() == pytest.approx(1650.0)
    assert r.limpo["speed_kmh"].max() == pytest.approx(8.0)
    assert m.motor_h == pytest.approx(1.0, abs=0.01)
    assert m.delta_horimetro_h is not None
    assert m.motor_h == pytest.approx(m.delta_horimetro_h, abs=0.02)
    assert m.litros_integral == pytest.approx(22.0, rel=0.01)
    assert not r.qualidade.problemas


def test_d1_motor_ligado_sem_rpm_usa_vazao_e_depois_horimetro() -> None:
    sem_rpm = _processar(Cenario(minutos=30, omitir=frozenset({"engine_rpm"})))
    assert sem_rpm.sanitizacao["motor_fonte_vazao"] > 0
    assert sem_rpm.metricas is not None
    assert sem_rpm.metricas.motor_h == pytest.approx(0.5, abs=0.01)

    so_horimetro = _processar(
        Cenario(minutos=30, nao_disponivel=frozenset({"engine_rpm", "fuel_rate_lph"}))
    )
    assert so_horimetro.sanitizacao["motor_fonte_horimetro"] > 0
    assert so_horimetro.metricas is not None
    assert so_horimetro.metricas.motor_h == pytest.approx(0.5, abs=0.05)


def test_d1_horimetro_x_motor_inconsistente_rebaixa_qualidade_e_alerta() -> None:
    """Se ainda assim o motor sair errado, a sessão não é publicada como boa."""
    dados = construir(Cenario(minutos=60))
    s = JohnDeereGen4Adapter().parse(io.BytesIO(dados), ParseContext("s.jdl"))
    df = s.amostras.copy()  # type: ignore[union-attr]
    df["engine_rpm"] = 300.0  # leitura errada, presente e abaixo do limiar o tempo todo
    df["fuel_rate_lph"] = np.nan
    df["engine_on"] = pd.array([pd.NA] * len(df), dtype="boolean")
    limpo, relatorio = sanitizar(df)
    m = calcular_metricas(limpo, 4.95)
    assert m is not None and m.motor_h < 0.1 and (m.delta_horimetro_h or 0) > 0.9
    q = avaliar(limpo, m, relatorio, [])
    assert q.tem("HORIMETRO_DIVERGE")
    assert q.score <= 50
    alertas = rules.de_qualidade("abc", q, limpo["ts"].iloc[0], limpo["ts"].iloc[-1])
    assert [a.tipo for a in alertas] == ["qualidade_dado"]
    assert alertas[0].severidade == "alto"


# ----------------------------------------------------------------- defeito 2
def test_d2_sessao_curta_nao_compara_contador_com_integral() -> None:
    """< 2 min: o contador anda em degraus de 0,5 L e "diverge" de 0,1 L integrados."""
    r = _processar(Cenario(minutos=1.5, vazao_lph=lambda _t: 4.0))
    m = r.metricas
    assert m is not None and m.litros_integral is not None
    assert not r.qualidade.tem("CONTADOR_DIVERGE")
    assert "contador_divergente" not in [a.tipo for a in r.alertas]


def test_d2_sessao_longa_com_divergencia_real_gera_alerta() -> None:
    dados = construir(Cenario(minutos=60))
    s = JohnDeereGen4Adapter().parse(io.BytesIO(dados), ParseContext("s.jdl"))
    df = s.amostras.copy()  # type: ignore[union-attr]
    df["fuel_rate_lph"] = df["fuel_rate_lph"] * 0.6  # sensor de vazão subestimando 40%
    limpo, relatorio = sanitizar(df)
    m = calcular_metricas(limpo, 4.95)
    q = avaliar(limpo, m, relatorio, [])
    assert q.tem("CONTADOR_DIVERGE")
    tipos = [
        a.tipo for a in rules.de_qualidade("abc", q, limpo["ts"].iloc[0], limpo["ts"].iloc[-1])
    ]
    assert tipos == ["contador_divergente"]


def test_d2_contador_e_integral_concordam_em_sessao_normal() -> None:
    m = _processar(Cenario(minutos=90)).metricas
    assert m is not None and m.litros_contador is not None and m.litros_integral is not None
    assert m.litros_contador / m.litros_integral == pytest.approx(1.0, abs=0.02)


# ----------------------------------------------------------------- defeito 3
@pytest.mark.parametrize("rumo", [0, 90, 180, 225, 270])
@pytest.mark.parametrize("gps", ["trilha", "caixa"])
def test_d3_trator_a_9kmh_nao_gera_salto_de_gps(rumo: int, gps: str) -> None:
    """165 de 169 alertas eram falsos: cantos da caixa lidos como fim/início de trajetória."""
    r = _processar(Cenario(minutos=20, velocidade_kmh=lambda _t: 9.0, rumo_graus=rumo, gps=gps))
    assert r.sessao.diagnostico.fonte_posicao == (
        "trilha_gps" if gps == "trilha" else "caixa_do_bloco"
    )
    assert [a for a in r.alertas if a.tipo == "gps_salto"] == []


def test_d3_salto_real_continua_detectado() -> None:
    r = _processar(Cenario(minutos=5, teleporte_em_s=120.0))
    saltos = [a for a in r.alertas if a.tipo == "gps_salto"]
    assert len(saltos) == 1
    assert saltos[0].detalhes["distancia_m"] == pytest.approx(2000, rel=0.05)
    assert saltos[0].valor is not None and saltos[0].valor > 40


def test_d3_lacuna_longa_de_gps_nao_e_salto() -> None:
    """Retomar 300 m adiante após 2 min sem posição é deslocamento normal (9 km/h)."""
    t = pd.date_range("2026-04-30 10:00", periods=181, freq="s", tz="UTC")
    lat = np.full(181, np.nan)
    lat[0], lat[180] = -28.1, -28.1 + 300 / 111_320
    df = pd.DataFrame({"ts": t, "lat": lat, "lon": -52.9, "gps_valid": ~np.isnan(lat)})
    assert rules.gps_salto("abc", df, rules.ConfigRegras()) == []
    assert math.isfinite(300 / 180 * 3.6)
