"""Adapter ISOXML (ISOBUS): um TLG da pasta TASKDATA -> schema universal a 1 Hz.

Serve para qualquer monitor que exporte ISO 11783-10 (Stara, Jacto, Case IH, New Holland,
Massey, Kuhn, Topcon, Trimble...). Os DDIs usados são os padronizados na ISO 11783-11:

* 148 Total Fuel Consumption (ml) e 149 Instantaneous Fuel Consumption per Time (mm³/s);
* 67 Actual Working Width (mm);
* 2 Actual Volume Per Area Application Rate (mm³/m² = 0,01 L/ha), que marca pulverização.

Velocidade vem da trilha GPS (distância/tempo): não depende de DDI de fabricante. Sem amostra
real de cada marca, o que muda entre monitores fica no diagnóstico (DDIs presentes).
"""

from __future__ import annotations

import hashlib
from typing import BinaryIO

import numpy as np
import pandas as pd

from sistemacampero.domain.ingestao import desempacotar_isoxml, eh_pacote_isoxml
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
from sistemacampero.infrastructure.parsers.isoxml.tlg import (
    IsoxmlFormatError,
    ler_taskdata,
    ler_tlg,
)

ADAPTER = "isoxml"
VERSAO = "1.0.0"
MAX_FILL_S = 5

DDI_COMBUSTIVEL_TOTAL = 148  # ml
DDI_COMBUSTIVEL_VAZAO = 149  # mm³/s
DDI_LARGURA = 67  # mm
DDI_TAXA_VOLUME = 2  # mm³/m²


class IsoxmlAdapter:
    """Pasta TASKDATA de monitor ISOBUS (um arquivo do Serrano por TLG gravado)."""

    brand = "isobus"
    technology = "isoxml"
    version = VERSAO

    def can_parse(self, head: bytes, filename: str) -> bool:
        return eh_pacote_isoxml(head)

    def parse(self, data: BinaryIO, ctx: ParseContext) -> ParsedSession | EmptyFile:
        bruto = data.read()
        sha = hashlib.sha256(bruto).hexdigest()
        try:
            nome, taskdata, cabecalho, binario = desempacotar_isoxml(bruto)
            tlg = ler_tlg(nome, cabecalho, binario)
            tarefa = ler_taskdata(taskdata, nome)
        except (IsoxmlFormatError, ValueError) as exc:
            raise ArquivoInvalido(f"{ctx.nome_arquivo}: {exc}") from exc

        dispositivo = next(
            (tarefa.dispositivos[d] for d in tlg.dets if d and d in tarefa.dispositivos), None
        )
        serial = (dispositivo or {}).get("serial")
        if not tlg.registros:
            return EmptyFile(
                sha,
                ADAPTER,
                VERSAO,
                "sem_blocos_de_dados",
                "Só cabeçalho: o monitor abriu a tarefa e não gravou registros.",
                serial,
            )

        diag = Diagnostico(fonte_posicao="trilha_gps")
        diag.contadores["registros"] = len(tlg.registros)
        diag.canais["ddis"] = {"presentes": sorted(set(tlg.ddis))}
        df = pd.DataFrame(
            {
                "ts": pd.to_datetime([r.ts for r in tlg.registros], utc=True),
                "lat": [r.posicao.get("A", np.nan) for r in tlg.registros],
                "lon": [r.posicao.get("B", np.nan) for r in tlg.registros],
                **{
                    f"ddi_{d}": [r.valores.get(d, np.nan) for r in tlg.registros]
                    for d in set(tlg.ddis)
                },
            }
        )
        amostras = self._por_segundo(df, diag)
        largura = None
        if f"ddi_{DDI_LARGURA}" in df and df[f"ddi_{DDI_LARGURA}"].notna().any():
            largura = float(df[f"ddi_{DDI_LARGURA}"].median()) / 1000.0
        operacao = None
        if f"ddi_{DDI_TAXA_VOLUME}" in df and df[f"ddi_{DDI_TAXA_VOLUME}"].gt(0).any():
            operacao = "pulverizacao"
            taxa = df[f"ddi_{DDI_TAXA_VOLUME}"].where(lambda s: s > 0) * 0.01
            diag.canais["aplicacao"] = {"taxa_media_l_ha": round(float(taxa.mean()), 1)}
        meta = MetadadosSessao(
            fabricante=(dispositivo or {}).get("designacao") or "ISOBUS",
            serial_maquina=serial,
            inicio=amostras["ts"].iloc[0].to_pydatetime(),
            fim=amostras["ts"].iloc[-1].to_pydatetime(),
            cliente_nome=tarefa.cliente,
            fazenda_nome=tarefa.fazenda,
            fazenda_guid=f"isoxml:{tarefa.fazenda}" if tarefa.fazenda else None,
            talhao_nome=tarefa.talhao,
            talhao_guid=f"isoxml:{tarefa.talhao}" if tarefa.talhao else None,
            implemento_nome=tarefa.nome,
            implemento_largura_m=largura,
            operacao=operacao,
        )
        return ParsedSession(sha, ADAPTER, VERSAO, meta, amostras, diag)

    @staticmethod
    def _por_segundo(df: pd.DataFrame, diag: Diagnostico) -> pd.DataFrame:
        df = df.sort_values("ts", kind="stable")
        df["ts"] = df["ts"].dt.floor("s")
        seg = df.groupby("ts").agg("last")  # o monitor pode gravar a 5 Hz
        grade = pd.date_range(seg.index[0], seg.index[-1], freq="1s")
        seg = seg.reindex(grade).ffill(limit=MAX_FILL_S).rename_axis("ts").reset_index()
        validos = seg["lat"].between(-90, 90) & seg["lon"].between(-180, 180)
        validos &= (seg["lat"].abs() > 1e-6) | (seg["lon"].abs() > 1e-6)
        seg["gps_valid"] = validos.fillna(False).astype(bool)
        seg.loc[~seg["gps_valid"], ["lat", "lon"]] = np.nan
        # Velocidade pela trilha (km/h), média móvel de 3 s para tirar o ruído do GPS.
        passo = np.r_[np.nan, distancias_m(seg["lat"].to_numpy(), seg["lon"].to_numpy())]
        seg["speed_kmh"] = pd.Series(passo * 3.6).rolling(3, min_periods=1, center=True).mean()
        diag.canais["speed_kmh"] = {"origem": "trilha GPS"}
        vazao, total = f"ddi_{DDI_COMBUSTIVEL_VAZAO}", f"ddi_{DDI_COMBUSTIVEL_TOTAL}"
        if vazao in seg and seg[vazao].notna().any():
            seg["fuel_rate_lph"] = seg[vazao] * 3.6e-3  # mm³/s -> L/h
            diag.canais["fuel_rate_lph"] = {"origem": "DDI 149"}
        if total in seg and seg[total].notna().any():
            seg["fuel_total_l"] = seg[total] / 1000.0
            diag.canais["fuel_total_l"] = {"origem": "DDI 148"}
            if "fuel_rate_lph" not in seg:
                seg["fuel_rate_lph"] = (seg["fuel_total_l"].diff() * 3600).clip(lower=0)
                diag.canais["fuel_rate_lph"] = {"origem": "derivada do DDI 148"}
        for c in ("fuel_rate_lph", "engine_rpm", "engine_hours", "engine_load_pct"):
            if c not in diag.canais:
                diag.canais_ausentes.append(c)
        diag.contadores["segundos"] = len(seg)
        return no_schema_universal(seg)
