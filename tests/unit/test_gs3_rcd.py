"""Casos do formato EvenByteDelta que o gerador padrão não exercita."""

from __future__ import annotations

import struct

import pytest

from sistemacampero.infrastructure.parsers.john_deere_gs3.rcd import (
    RcdFormatError,
    ler_fdd,
    ler_fdl,
)
from tests.sinteticos import gs3


def _registro(
    omitidas: int, b: int, medidas: list[int], lat: int, elapsed: int, crus: list[float]
) -> bytes:
    reg = struct.pack("<HBBI", 2, 1, omitidas, 0x70) + (0).to_bytes(4, "little")
    reg += b.to_bytes(3, "little")
    reg += b"".join(struct.pack("<h", v) for v in medidas)  # colunas não omitidas
    reg += struct.pack("<6H", 0, 0, 0, 0, 0, 0)
    if not (b >> 2) & 1:  # latitude no bloco fixo (bit 2 = coluna 10)
        reg += struct.pack("<i", lat)
    reg += struct.pack("<ih", 0, 0) + struct.pack("<i", elapsed)
    reg += struct.pack("<2Hf", 3, 4, 2.0)
    return reg + b"".join(struct.pack("<2Hd", 3, 8, v) for v in crus)


def test_registro_de_evento_zera_as_medidas_omitidas() -> None:
    fdd = gs3._cabecalho()
    fdd += _registro(0, 0b11, [250, 4000], 0, 0, [22.0, 8.0])  # 17,5 % e 4 kg
    fdd += _registro(0b11, 0, [], 0, 200, [])  # evento: sem umidade e massa
    fdd += _registro(0, 0, [260, 3900], 0, 1000, [])  # recomeça do zero
    [bloco] = ler_fdd(fdd)
    umidade = [r[0] for r in bloco.linhas]
    assert umidade == pytest.approx([17.5, 15.0, 17.6])
    assert bloco.linhas[2][1] == pytest.approx(3.9)


def test_valor_absoluto_quando_o_delta_nao_cabe() -> None:
    fdd = gs3._cabecalho()
    fdd += _registro(0, 0b11, [0, 0], 1000, 0, [22.0, 8.0])
    fdd += _registro(0, 0b100, [0, 0], 0, 1000, [-27.5])  # latitude vem crua (bit 2)
    fdd += _registro(0, 0, [0, 0], 10, 1000, [])  # e o delta segue a partir dela
    [bloco] = ler_fdd(fdd)
    lat = [r[10] for r in bloco.linhas]
    assert lat == pytest.approx([-28.1 + 1e-6, -27.5, -27.5 + 1e-8])


def test_fdl_traz_inicio_largura_e_cadastro() -> None:
    fdl = ler_fdl(gs3.construir_fdl())
    assert fdl.inicios == [gs3.INICIO]
    assert fdl.largura_m == pytest.approx(7.6)
    assert (fdl.serial_maquina, fdl.modelo, fdl.talhao[0]) == (
        "1CQS540ATG0000001",
        "S540",
        "Talhao Teste",
    )


def test_truncado_e_erro_de_formato() -> None:
    fdd = gs3.construir_fdd(gs3.CenarioGs3(minutos=1))
    with pytest.raises(RcdFormatError):
        ler_fdd(fdd[:-30])
