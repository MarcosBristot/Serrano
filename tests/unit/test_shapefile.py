"""Leitor de perímetro em shapefile (OMNI do pulverizador)."""

from __future__ import annotations

import pytest

from sistemacampero.domain.errors import Invalido
from sistemacampero.infrastructure.parsers.shapefile import ler_perimetro, nome_normalizado
from tests.sinteticos.shp import PRJ_UTM, PRJ_WGS84, poligono_shp, quadrado


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
