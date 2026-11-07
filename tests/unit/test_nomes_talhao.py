"""A mesma lavoura escrita por monitores diferentes vira um talhão só."""

from __future__ import annotations

import pytest

from sistemacampero.domain.services.nomes import chave_talhao, mesmo_talhao


@pytest.mark.parametrize(
    ("nome", "chave"),
    [
        ("Mãe", "mae"),
        ("Mae_Aveia22", "mae"),
        ("Bira_Trigo23", "bira"),
        ("Cabana_aveia", "cabana"),
        ("Tio_Jorge_aveia23", "tiojorge"),
        ("TioJorge_Trigo22", "tiojorge"),
        ("Paulo 3,7", "paulo37"),
        ("Paulo3.7_Aveia22", "paulo37"),
        ("Coxilha_Grand_Soja22", "coxilhagrand"),
        ("Sede_trigo23", "sede"),
        ("Soja", "soja"),  # o nome todo é a cultura: fica como está
        ("1", "1"),
    ],
)
def test_chave(nome: str, chave: str) -> None:
    assert chave_talhao(nome) == chave


def test_nome_cortado_pelo_monitor_e_o_mesmo_talhao() -> None:
    assert mesmo_talhao(chave_talhao("CoxilhaGrand_Trigo22"), chave_talhao("Coxilha Grande"))
    assert not mesmo_talhao(chave_talhao("Paulo"), chave_talhao("Paulo 3,7"))  # curto demais
    assert not mesmo_talhao(chave_talhao("paulo3,8"), chave_talhao("Paulo 3,7"))
