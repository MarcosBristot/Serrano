"""Contornos, localização de talhão, área por cobertura e importador Gen4 (sem banco)."""

from __future__ import annotations

import json
import math
import uuid

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, box

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.services.coverage import calcular_cobertura, zona_utm
from sistemacampero.domain.services.geo import (
    Contorno,
    LocalizadorDeTalhoes,
    area_geodesica_ha,
    normalizar_contorno,
)
from sistemacampero.infrastructure.parsers.john_deere_gen4.masterdata import ler_cadastro_gen4
from tests.sinteticos.gen4 import QUADRADO, gjson_boundary, masterdata_xml

M_POR_GRAU_LAT = 111_320.0


# ------------------------------------------------------------------ contornos
def test_normaliza_polygon_feature_e_featurecollection_do_monitor() -> None:
    poly = {"type": "Polygon", "coordinates": [QUADRADO]}
    assert isinstance(normalizar_contorno(poly), MultiPolygon)
    assert normalizar_contorno({"type": "Feature", "geometry": poly, "properties": {}}).equals(
        normalizar_contorno(poly)
    )
    fc = json.loads(gjson_boundary(QUADRADO))
    multi = normalizar_contorno(fc)
    assert len(multi.geoms) == 1  # só o Exterior; a cabeceira é ignorada
    assert area_geodesica_ha(multi) == pytest.approx(area_geodesica_ha(normalizar_contorno(poly)))


def test_contorno_auto_intersectante_e_corrigido() -> None:
    gravata = {
        "type": "Polygon",
        "coordinates": [
            [[-52.9, -28.1], [-52.89, -28.09], [-52.89, -28.1], [-52.9, -28.09], [-52.9, -28.1]]
        ],
    }
    m = normalizar_contorno(gravata)
    assert m.is_valid and area_geodesica_ha(m) > 1


@pytest.mark.parametrize(
    "ruim",
    [
        {"type": "Point", "coordinates": [-52.9, -28.1]},
        {
            "type": "Polygon",
            "coordinates": [[[-5290, -2810], [-5289, -2810], [-5289, -2809], [-5290, -2810]]],
        },
        {"type": "Polygon", "coordinates": [[[0, 0], [1e-7, 0], [1e-7, 1e-7], [0, 0]]]},
        {"type": "Nada"},
        "não é json",
    ],
)
def test_contorno_invalido(ruim: object) -> None:
    with pytest.raises((Invalido, ValueError)):
        normalizar_contorno(ruim)  # type: ignore[arg-type]


# ------------------------------------------------------------------ localização
def _contornos() -> tuple[uuid.UUID, uuid.UUID, LocalizadorDeTalhoes]:
    a, b = uuid.uuid4(), uuid.uuid4()
    loc = LocalizadorDeTalhoes(
        [
            Contorno(a, box(-52.93, -28.11, -52.91, -28.09)),
            Contorno(b, box(-52.91, -28.11, -52.89, -28.09)),
        ]
    )
    return a, b, loc


def test_talhao_da_maioria_dos_pontos_de_trabalho() -> None:
    a, b, loc = _contornos()
    lon = np.r_[np.full(70, -52.92), np.full(30, -52.90), np.full(5, np.nan)]
    lat = np.full(105, -28.10)
    trabalho = np.r_[np.ones(70, bool), np.ones(30, bool), np.zeros(5, bool)]
    r = loc.localizar(lat, lon, trabalho)
    assert r.talhao_id == a and r.confianca == pytest.approx(0.7)
    assert r.por_ponto[0] == a and r.por_ponto[80] == b and r.por_ponto[-1] is None


def test_manobra_nao_decide_o_talhao() -> None:
    a, b, loc = _contornos()
    lon = np.r_[np.full(60, -52.92), np.full(40, -52.90)]
    trabalho = np.r_[np.zeros(60, bool), np.ones(40, bool)]  # trabalhou só no B
    assert loc.localizar(np.full(100, -28.10), lon, trabalho).talhao_id == b


def test_fora_de_todos_e_sem_contornos() -> None:
    _, _, loc = _contornos()
    r = loc.localizar(np.array([-29.0]), np.array([-52.0]), np.array([True]))
    assert r.talhao_id is None and r.confianca == 0
    vazio = LocalizadorDeTalhoes([])
    assert (
        vazio.vazio
        and vazio.localizar(np.array([-28.1]), np.array([-52.9]), np.array([True])).talhao_id
        is None
    )


# ------------------------------------------------------------------ cobertura
def _passadas(n: int, comprimento_m: float, espacamento_m: float, hz: int = 1) -> pd.DataFrame:
    """Trator em vai-e-vem norte/sul a 8 km/h, faixas paralelas a cada espaçamento."""
    passo = 8 / 3.6 / hz
    lat0, lon0 = -28.10, -52.92
    m_lon = M_POR_GRAU_LAT * math.cos(math.radians(lat0))
    lats, lons = [], []
    for i in range(n):
        ida = np.arange(0, comprimento_m, passo)
        trecho = ida if i % 2 == 0 else ida[::-1]
        lats += list(lat0 + trecho / M_POR_GRAU_LAT)
        lons += [lon0 + i * espacamento_m / m_lon] * len(trecho)
    k = len(lats)
    return pd.DataFrame(
        {
            "ts": pd.date_range("2026-04-30", periods=k, freq="s", tz="UTC"),
            "lat": lats,
            "lon": lons,
            "gps_valid": True,
            "speed_kmh": 8.0,
            "engine_on": True,
        }
    )


def test_cobertura_sem_sobreposicao_bate_com_a_estimada() -> None:
    df = _passadas(n=5, comprimento_m=500, espacamento_m=5.0)
    c = calcular_cobertura(df, largura_m=5.0)
    assert c is not None
    # 5 faixas de 500 m x 5 m = 1,25 ha (as viradas entre faixas são lacunas de posição).
    assert c.area_ha == pytest.approx(1.25, rel=0.02)
    assert c.sobreposicao_pct == pytest.approx(0, abs=1)
    assert c.geometria.is_valid and isinstance(c.geometria, MultiPolygon)


def test_sobreposicao_conta_uma_vez_so() -> None:
    df = _passadas(n=5, comprimento_m=500, espacamento_m=2.5)  # metade da largura
    c = calcular_cobertura(df, largura_m=5.0)
    assert c is not None
    assert c.area_bruta_ha == pytest.approx(1.25, rel=0.02)
    assert c.area_ha == pytest.approx(0.75, rel=0.03)  # 4 x 2,5 m + 5 m de largura útil
    assert c.sobreposicao_pct == pytest.approx(40, abs=2)


def test_recorte_pelo_talhao() -> None:
    df = _passadas(n=4, comprimento_m=400, espacamento_m=5.0)
    metade = box(-52.93, -28.10, -52.90, -28.10 + 200 / M_POR_GRAU_LAT)
    c = calcular_cobertura(df, 5.0, metade)
    assert c is not None
    assert c.area_ha == pytest.approx(0.8, rel=0.03)  # a área da sessão é a total
    assert c.dentro_do_talhao_ha == pytest.approx(0.4, rel=0.03)


def test_sem_largura_sem_gps_ou_parado_nao_calcula() -> None:
    df = _passadas(n=2, comprimento_m=200, espacamento_m=5.0)
    assert calcular_cobertura(df, None) is None
    assert calcular_cobertura(df.assign(gps_valid=False), 5.0) is None
    assert calcular_cobertura(df.assign(speed_kmh=0.0), 5.0) is None


def test_salto_de_gps_quebra_o_trecho() -> None:
    df = _passadas(n=1, comprimento_m=300, espacamento_m=5.0)
    df.loc[60:, "lon"] += 0.01  # 1 km para leste no meio da passada
    c = calcular_cobertura(df, 5.0)
    assert c is not None and c.area_ha == pytest.approx(0.15, rel=0.05)  # sem a "ponte" de 1 km


def test_zona_utm_de_passo_fundo() -> None:
    assert zona_utm(-52.4, -28.26).to_epsg() == 32722


# ------------------------------------------------------------------ importador Gen4
def test_importa_masterdata_e_contornos() -> None:
    xml = masterdata_xml()
    r = ler_cadastro_gen4(xml, {"Boundary{b1}.gjson": gjson_boundary(QUADRADO)})
    assert [(f.guid, f.nome, f.cliente_nome) for f in r.fazendas] == [
        ("f1", "Fazenda Teste", "Cliente Teste")
    ]
    talhoes = {t.nome: t for t in r.talhoes}
    assert set(talhoes) == {"Talhao Teste", "Sem Contorno"}
    assert talhoes["Talhao Teste"].guid == "tal" and talhoes["Talhao Teste"].fazenda_guid == "f1"
    assert talhoes["Talhao Teste"].contorno is not None and talhoes["Sem Contorno"].contorno is None
    assert [(i.nome, i.largura_m) for i in r.implementos] == [
        ("Plantadeira Teste", 4.95),
        ("Por Linhas", 4.5),
    ]
    assert [o.nome for o in r.operadores] == ["Operador Teste"]


def test_masterdata_com_dtd_e_recusado() -> None:
    bomba = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><SetupFile>&a;</SetupFile>'
    with pytest.raises(Invalido) as exc:
        ler_cadastro_gen4(bomba, {})
    assert exc.value.codigo == "MASTERDATA_INVALIDO"
    with pytest.raises(Invalido):
        ler_cadastro_gen4(b"<nao fecha", {})


def test_contorno_citado_mas_ausente_vira_aviso() -> None:
    r = ler_cadastro_gen4(masterdata_xml(), {})
    assert any("não veio no pendrive" in a for a in r.avisos)
