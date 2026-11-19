"""Adapter Trimble TMX-2050 / PTx: registro de GPS (``*_LogAg_*.tsip``) -> schema universal a 1 Hz.

É o monitor da Massey Ferguson (e de outras marcas AGCO, Valtra e Fendt) e de tratores de várias
marcas com piloto Trimble. As tarefas, talhões e implementos (pasta ``AgData``) vêm CRIPTOGRAFADOS
pelo fabricante e não são lidos. O que se lê é a pasta ``Diagnostics``:

* o arquivo é um fluxo TSIP (protocolo público da Trimble): pacotes ``DLE id ... DLE ETX``;
* o pacote ``0x1A`` carrega frases NMEA 0183 (padrão aberto): ``GGA`` (posição, qualidade do
  GPS), ``VTG`` (velocidade) e ``RMC``/``ZDA`` (data). Como NMEA é ASCII e nunca contém o byte
  ``DLE``, as frases são achadas direto no fluxo, sem desmontar os pacotes (16 MB em ~0,5 s);
* não há consumo de diesel, rotação nem horímetro: esses canais ficam ``NaN``
  (``canais_fora_do_formato``) e o motor conta como ligado enquanto o monitor registra
  (o monitor liga com a chave do trator).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from typing import BinaryIO

import numpy as np
import pandas as pd

from sistemacampero.domain.services.geo import distancias_m
from sistemacampero.domain.telemetry import (
    ArquivoInvalido,
    Diagnostico,
    EmptyFile,
    MetadadosSessao,
    ParseContext,
    ParsedSession,
    no_schema_universal,
)

ADAPTER = "trimble_tmx"
VERSAO = "1.0.0"
MAX_FILL_S = 5
DLE = 0x10

# "TMX_LogAg_6435439113_20261111_1455_003.tsip"; o modelo vem antes, quando a expansão do zip
# acha o veículo em AgData/Vehicles: "Massey Ferguson 7725 · TMX_LogAg_...tsip".
_NOME = re.compile(r"(?:(?P<modelo>.+?) · )?(?P<produto>TMX|PTx)_LogAg_(?P<serial>\d+)_", re.I)
_FRASE = re.compile(rb"\$G[PNLA](GGA|VTG|RMC|ZDA),([^*\r\n]*)\*[0-9A-Fa-f]{2}")
# Marcas que aparecem no nome do veículo do monitor (o resto fica como "Trimble").
_MARCAS = (
    "Massey Ferguson",
    "Valtra",
    "Fendt",
    "Challenger",
    "John Deere",
    "Case IH",
    "New Holland",
    "Jacto",
    "Stara",
    "Agrale",
    "LS Tractor",
    "Mahindra",
    "Kubota",
    "Claas",
)


def _graus(valor: str, hemisferio: str) -> float:
    """ddmm.mmmm (NMEA) -> graus decimais."""
    if not valor:
        return float("nan")
    ponto = valor.index(".") if "." in valor else len(valor)
    graus = float(valor[: ponto - 2]) + float(valor[ponto - 2 :]) / 60.0
    return -graus if hemisferio in ("S", "W") else graus


def _hora(campo: str) -> timedelta | None:
    if len(campo) < 6:
        return None
    return timedelta(hours=int(campo[0:2]), minutes=int(campo[2:4]), seconds=float(campo[4:]))


def ler_nmea(nmea: bytes) -> pd.DataFrame:
    """Uma linha por GGA válido: ts (UTC), lat, lon, qualidade e a velocidade do VTG seguinte."""
    dia: date | None = None
    linhas: list[dict[str, object]] = []
    for m in _FRASE.finditer(nmea):
        tipo, campos = m.group(1), m.group(2).decode("ascii", "replace").split(",")
        try:
            if tipo == b"RMC" and len(campos) > 8 and len(campos[8]) == 6:
                d = campos[8]
                dia = date(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
            elif tipo == b"ZDA" and len(campos) > 3 and campos[3]:
                dia = date(int(campos[3]), int(campos[2]), int(campos[1]))
            elif tipo == b"GGA" and len(campos) > 5:
                hora = _hora(campos[0])
                qualidade = int(campos[5] or 0)
                if dia is None or hora is None or qualidade == 0:
                    continue
                linhas.append(
                    {
                        "ts": datetime(dia.year, dia.month, dia.day, tzinfo=UTC) + hora,
                        "lat": _graus(campos[1], campos[2]),
                        "lon": _graus(campos[3], campos[4]),
                        "qualidade": qualidade,
                        "vtg_kmh": np.nan,
                    }
                )
            elif tipo == b"VTG" and linhas and len(campos) > 6 and campos[6]:
                linhas[-1]["vtg_kmh"] = float(campos[6])
        except (ValueError, IndexError):
            continue  # frase truncada no corte do arquivo
    return pd.DataFrame(linhas, columns=["ts", "lat", "lon", "qualidade", "vtg_kmh"])


def _modelo_e_marca(nome_arquivo: str) -> tuple[str | None, str, str | None]:
    m = _NOME.search(nome_arquivo or "")
    modelo = re.sub(r"\s+", " ", m.group("modelo")).strip() if m and m.group("modelo") else None
    serial = m.group("serial") if m else None
    marca = next((x for x in _MARCAS if modelo and modelo.lower().startswith(x.lower())), "Trimble")
    return modelo, marca, serial


class TrimbleTmxAdapter:
    """Monitor Trimble TMX-2050/PTx: um arquivo do Serrano por registro *_LogAg_*.tsip."""

    brand = "trimble"
    technology = "tmx"
    version = VERSAO

    def can_parse(self, head: bytes, filename: str) -> bool:
        nome = (filename or "").lower()
        return nome.endswith(".tsip") and "_logag_" in nome and head[:1] == bytes([DLE])

    def parse(self, data: BinaryIO, ctx: ParseContext) -> ParsedSession | EmptyFile:
        bruto = data.read()
        sha = hashlib.sha256(bruto).hexdigest()
        # Registro cortado no fim (monitor desligado no meio) é normal e é lido; sem nenhum fim de
        # pacote (DLE ETX) no começo do arquivo, não é TSIP.
        if not bruto or bruto[0] != DLE or b"" not in bruto[:65536]:
            raise ArquivoInvalido(f"{ctx.nome_arquivo}: não é um registro TSIP da Trimble.")
        modelo, marca, serial = _modelo_e_marca(ctx.nome_arquivo)
        serial_maquina = f"trimble-{serial}" if serial else None
        pontos = ler_nmea(bruto)
        if pontos.empty:
            return EmptyFile(
                sha,
                ADAPTER,
                VERSAO,
                "sem_posicao_gps",
                "Registro do monitor sem posição de GPS válida (monitor ligado sem sinal).",
                serial_maquina,
            )

        diag = Diagnostico(fonte_posicao="trilha_gps")
        diag.contadores["frases_gga"] = len(pontos)
        diag.contadores["gps_rtk"] = int((pontos["qualidade"] == 4).sum())
        amostras = self._por_segundo(pontos, diag)
        diag.avisos.append(
            "Monitor Trimble: tarefas e implementos vêm criptografados; motor considerado ligado "
            "enquanto o monitor registra."
        )
        meta = MetadadosSessao(
            fabricante=marca,
            modelo=modelo,
            serial_maquina=serial_maquina,
            serial_monitor=serial,
            inicio=amostras["ts"].iloc[0].to_pydatetime(),
            fim=amostras["ts"].iloc[-1].to_pydatetime(),
        )
        return ParsedSession(sha, ADAPTER, VERSAO, meta, amostras, diag)

    @staticmethod
    def _por_segundo(pontos: pd.DataFrame, diag: Diagnostico) -> pd.DataFrame:
        df = pontos.sort_values("ts", kind="stable").copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.floor("s")
        seg = df.groupby("ts").agg("last")
        grade = pd.date_range(seg.index[0], seg.index[-1], freq="1s")
        seg = seg.reindex(grade).ffill(limit=MAX_FILL_S).rename_axis("ts").reset_index()
        validos = seg["lat"].between(-90, 90) & seg["lon"].between(-180, 180)
        validos &= (seg["lat"].abs() > 1e-6) | (seg["lon"].abs() > 1e-6)
        seg["gps_valid"] = validos.fillna(False).astype(bool)
        seg.loc[~seg["gps_valid"], ["lat", "lon"]] = np.nan
        # Velocidade do próprio receptor (VTG); sem VTG, pela trilha.
        if seg["vtg_kmh"].notna().any():
            seg["speed_kmh"] = seg["vtg_kmh"]
            diag.canais["speed_kmh"] = {"origem": "NMEA VTG (receptor GNSS)"}
        else:
            passo = np.r_[np.nan, distancias_m(seg["lat"].to_numpy(), seg["lon"].to_numpy())]
            seg["speed_kmh"] = pd.Series(passo * 3.6).rolling(3, min_periods=1, center=True).mean()
            diag.canais["speed_kmh"] = {"origem": "trilha GPS"}
        # O monitor só registra com a chave ligada: segundo registrado = motor ligado.
        seg["engine_on"] = pd.array(seg["gps_valid"].to_numpy(), dtype="boolean")
        diag.canais["engine_on"] = {"origem": "monitor registrando"}
        diag.canais_fora_do_formato = [
            "fuel_rate_lph",
            "fuel_total_l",
            "engine_rpm",
            "engine_load_pct",
            "engine_hours",
        ]
        diag.contadores["segundos"] = len(seg)
        return no_schema_universal(seg)
