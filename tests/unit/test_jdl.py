"""Leitor de baixo nível do .jdl (âncoras, tempo, trilha GPS, caixa por bloco)."""

from __future__ import annotations

import pytest

from sistemacampero.infrastructure.parsers.john_deere_gen4.jdl import (
    JdlFormatError,
    read_jdl,
)
from tests.sinteticos.jdl_builder import CANAIS, Cenario, construir


def test_metadados_do_cabecalho() -> None:
    j = read_jdl(construir(Cenario(minutos=1)))
    assert j.software_version == "10.30.0-teste"
    assert j.machine_serial == "SINTETICO0001"
    assert (j.client_name, j.farm_name, j.field_name) == (
        "Cliente Teste",
        "Fazenda Teste",
        "Talhao Teste",
    )
    assert j.field_guid == "{tal}"
    assert j.implements[0].name == "Plantadeira Teste"
    assert j.implements[0].width_m == pytest.approx(4.95)


@pytest.mark.parametrize("ancora_inicial", [True, False])
def test_valores_fisicos_com_e_sem_ancora_inicial(ancora_inicial: bool) -> None:
    j = read_jdl(
        construir(Cenario(minutos=2, rpm=lambda t: 1500 + t, ancora_inicial=ancora_inicial))
    )
    s = j.series[CANAIS["engine_rpm"].cid]
    assert len(s.raw) == 2 * 60 * 5
    assert s.raw[0] / 8 == pytest.approx(1500.0)
    assert s.raw[-1] / 8 == pytest.approx(1500 + 119.8, abs=0.2)
    assert j.estatisticas["ancoras_divergentes"] == 0


def test_tempo_ancorado_por_bloco() -> None:
    j = read_jdl(construir(Cenario(minutos=2)))
    t = j.series[CANAIS["speed_kmh"].cid].t_ms
    assert t[0] == pytest.approx(200.0)  # 1ª amostra 200 ms após o início do bloco
    assert t[150] == pytest.approx(30_200.0)  # 2º bloco recomeça na âncora de 30 s
    assert [c.inicio_ms for c in j.chunks] == [0.0, 30_000.0, 60_000.0, 90_000.0]


def test_trilha_gps_e_caixa_do_bloco() -> None:
    j = read_jdl(construir(Cenario(minutos=1, velocidade_kmh=lambda _t: 9.0, rumo_graus=225)))
    g = j.gps
    assert len(g.t_ms) == 300
    assert g.t_ms[1] - g.t_ms[0] == pytest.approx(200.0)
    assert g.lat[0] == pytest.approx(-28.10, abs=1e-4)
    assert g.lat[-1] < g.lat[0] and g.lon[-1] < g.lon[0]  # andou para sudoeste
    for c in j.chunks:
        assert c.sudoeste is not None and c.nordeste is not None
        assert c.sudoeste[0] <= c.nordeste[0] and c.sudoeste[1] <= c.nordeste[1]


def test_sentinela_preservada_no_bruto() -> None:
    j = read_jdl(construir(Cenario(minutos=1, nao_disponivel=frozenset({"engine_rpm"}))))
    assert set(j.series[CANAIS["engine_rpm"].cid].raw) == {-(2**31)}


def test_so_cabecalho() -> None:
    j = read_jdl(construir(Cenario(minutos=1, so_cabecalho=True)))
    assert j.chunks == [] and j.series == {}
    assert j.started_at_ms is not None


def test_arquivo_truncado_gera_erro_claro() -> None:
    with pytest.raises(JdlFormatError):
        read_jdl(construir(Cenario(minutos=1))[:-10])


def test_filtro_de_canais() -> None:
    j = read_jdl(construir(Cenario(minutos=1)), channel_filter={CANAIS["speed_kmh"].cid})
    assert set(j.series) == {CANAIS["speed_kmh"].cid}
    assert len(j.gps.t_ms) == 300  # a trilha GPS é lida à parte
