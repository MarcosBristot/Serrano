"""Leitor de perímetro em shapefile (OMNI do pulverizador)."""

from __future__ import annotations

from datetime import datetime

import pytest

from sistemacampero.domain.errors import Invalido
from sistemacampero.infrastructure.parsers.shapefile import (
    ler_linhas,
    ler_perimetro,
    nome_normalizado,
)
from tests.sinteticos.shp import (
    PRJ_UTM,
    PRJ_WGS84,
    dbf,
    poligono_shp,
    polilinhas_shp,
    quadrado,
)


def test_anel_anti_horario_e_regravacao_viram_um_poligono() -> None:
    # O OMNI grava o externo no sentido anti-horário e repete o perímetro ao regravar.
    a = quadrado(-52.93, -28.12, 0.01)
    b = quadrado(-52.93005, -28.12005, 0.0101)  # regravação quase igual
    g = ler_perimetro(poligono_shp(a, b), PRJ_WGS84)
    assert len(g.geoms) == 1 and not g.geoms[0].interiors
    assert g.area == pytest.approx(0.0101**2, rel=1e-6)  # fica o maior


def test_furo_de_verdade_e_mantido() -> None:
    fora = quadrado(-52.93, -28.12, 0.01)
    mata = quadrado(-52.927, -28.117, 0.003, anti_horario=False)
    g = ler_perimetro(poligono_shp(fora, mata), PRJ_WGS84)
    assert len(g.geoms[0].interiors) == 1
    assert g.area == pytest.approx(0.01**2 - 0.003**2, rel=1e-6)


def test_projecao_nao_suportada_e_recusada() -> None:
    with pytest.raises(Invalido) as exc:
        ler_perimetro(poligono_shp(quadrado(-52.93, -28.12, 0.01)), PRJ_UTM)
    assert exc.value.codigo == "SHP_PROJECAO"


def test_nomes_normalizados() -> None:
    assert nome_normalizado("Mãe") == nome_normalizado("Mae") == "mae"
    assert nome_normalizado("Paulo 3,7") == nome_normalizado("Paulo3-7")
    assert nome_normalizado("Precisão") == nome_normalizado("PRECISAO")


def test_cabeceira_fica_so_a_ultima_regravacao() -> None:
    # O OMNI acrescenta registros sem acompanhar o .dbf: vale o último com forma.
    antiga = [(-52.0, -28.0), (-52.0, -28.01), (-52.01, -28.01)]
    atual = [(-52.0, -28.0), (-52.0, -28.02), (-52.02, -28.02), (-52.0, -28.0)]
    shp = polilinhas_shp([(-52.0, -28.0), (-52.0, -28.0001)], antiga, atual)
    tabela = dbf([("Headland", "C", 64)], [["2026/09/24 11:36:12"]])
    [cab] = ler_linhas(shp, tabela, PRJ_WGS84, "cabeceira")
    assert len(cab["geom"].coords) == 4
    assert cab["gravado_em"] == datetime(2026, 9, 24, 11, 36, 12)


def test_linhas_guia_com_tipo_e_data() -> None:
    reta = [(-52.0, -28.0), (-52.0, -28.01)]
    curva = [(-52.0, -28.0), (-52.001, -28.005), (-52.0, -28.01)]
    tabela = dbf(
        [("Runline", "C", 64), ("Type", "N", 5)],
        [["2022/07/22 14:27:52", "1"], ["2023/11/20 08:20:15", "0"]],
    )
    linhas = ler_linhas(polilinhas_shp(reta, curva), tabela, PRJ_WGS84, "linha_guia")
    assert [(x["subtipo"], len(x["geom"].coords)) for x in linhas] == [(1, 2), (0, 3)]
    assert linhas[1]["gravado_em"] == datetime(2023, 11, 20, 8, 20, 15)
