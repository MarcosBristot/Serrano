"""Quando cada manutenção vence pelo horímetro."""

from __future__ import annotations

import pytest

from sistemacampero.domain.manutencao import Situacao, prever


def test_em_dia_com_dias_de_trabalho_no_ritmo_atual() -> None:
    p = prever(250, ultima_h=600, horimetro_h=700, uso_h_dia=10)
    assert (p.proxima_h, p.faltam_h, p.situacao) == (850, 150, Situacao.EM_DIA)
    assert p.dias_trabalho == pytest.approx(15)


def test_proxima_dentro_da_margem_e_vencida_depois() -> None:
    assert prever(250, 600, 830, 8).situacao is Situacao.PROXIMA  # faltam 20 h (margem 25)
    vencida = prever(250, 600, 860, 8)
    assert vencida.situacao is Situacao.VENCIDA and vencida.dias_trabalho == 0


def test_agendar_quando_faltam_poucos_dias_de_trabalho() -> None:
    # 35 h é mais que a margem de 25 h, mas a 8 h por dia são só 4 dias de trabalho.
    assert prever(250, 600, 815, 8).situacao is Situacao.PROXIMA


def test_sem_horimetro_ou_sem_ultima_vez() -> None:
    assert prever(250, None, 700, 8).situacao is Situacao.SEM_REFERENCIA
    assert prever(250, 600, None, 8).situacao is Situacao.SEM_REFERENCIA
