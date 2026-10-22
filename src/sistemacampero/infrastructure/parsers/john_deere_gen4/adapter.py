"""Adapter John Deere Gen4: .jdl -> schema universal a 1 Hz."""

from __future__ import annotations

import math
from typing import BinaryIO

import numpy as np
import pandas as pd

from sistemacampero.domain.telemetry import (
    ArquivoInvalido,
    Diagnostico,
    EmptyFile,
    MetadadosSessao,
    ParseContext,
    ParsedSession,
    no_schema_universal,
    normalizar_guid,
)
from sistemacampero.infrastructure.parsers.john_deere_gen4 import channels as ch
from sistemacampero.infrastructure.parsers.john_deere_gen4.jdl import (
    ChannelDef,
    JdlFile,
    JdlFormatError,
    read_jdl,
)

ADAPTER = "john_deere_gen4"
VERSAO = "2.0.0"  # 2.x: âncoras de valor/tempo, trilha GPS de 5 Hz, caixa por bloco
MAX_FILL_S = 5  # preenche no máximo 5 s de buraco em grandezas instantâneas


def _canal_do_trator(c: ChannelDef) -> bool:
    m = ch.DDI_TO_COLUMN.get(c.ddi)
    return m is not None and c.group in ch.TRACTOR_GROUPS and c.unit == m[1]


def _gps_plausivel(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    ok: np.ndarray = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (np.abs(lat) <= 90)
        & (np.abs(lon) <= 180)
        & ((np.abs(lat) > 1e-6) | (np.abs(lon) > 1e-6))
    )
    return ok


class JohnDeereGen4Adapter:
    """Monitor John Deere Gen4 (arquivos ``.jdl`` da pasta ``JD-Data/log``)."""

    brand = "john_deere"
    technology = "gen4"
    version = VERSAO

    def can_parse(self, head: bytes, filename: str) -> bool:
        return filename.lower().endswith(".jdl") and len(head) >= 5 and head[0] == 0x0D

    def parse(self, data: BinaryIO, ctx: ParseContext) -> ParsedSession | EmptyFile:
        bruto = data.read()
        try:
            jdl = read_jdl(bruto, channel_filter=_canal_do_trator)
        except JdlFormatError as exc:
            raise ArquivoInvalido(f"{ctx.nome_arquivo}: {exc}") from exc

        def vazio(motivo: str, explicacao: str) -> EmptyFile:
            return EmptyFile(jdl.sha256, ADAPTER, VERSAO, motivo, explicacao, jdl.machine_serial)

        if jdl.started_at_ms is None:
            return vazio("sem_horario_de_inicio", "Cabeçalho sem horário de início.")
        if not jdl.chunks:
            return vazio(
                "sem_blocos_de_dados",
                "Só cabeçalho: o monitor abriu o arquivo e não gravou nenhum bloco "
                "(comum ao ligar/desligar o monitor sem operar).",
            )
        diag = Diagnostico()
        colunas = self._colunas(jdl, diag)
        if not colunas:
            return vazio(
                "sem_canais_do_trator",
                "Há blocos, mas nenhuma amostra dos canais do trator (velocidade, vazão, "
                "RPM, horímetro, contador).",
            )

        t0 = pd.Timestamp(jdl.started_at_ms, unit="ms", tz="UTC")
        amostras = self._reamostrar(colunas, jdl, t0, diag)
        diag.contadores.update(jdl.estatisticas)
        if jdl.estatisticas.get("ancoras_divergentes"):
            diag.avisos.append(
                f"{jdl.estatisticas['ancoras_divergentes']} âncora(s) divergente(s): "
                "houve perda de amostras entre blocos (a série foi ressincronizada)."
            )

        impl = jdl.implements[0] if jdl.implements else None
        meta = MetadadosSessao(
            fabricante="John Deere",
            serial_maquina=jdl.machine_serial,
            inicio=amostras["ts"].iloc[0].to_pydatetime(),
            fim=amostras["ts"].iloc[-1].to_pydatetime(),
            serial_monitor=jdl.display_serial,
            firmware=jdl.software_version,
            cliente_nome=jdl.client_name,
            cliente_guid=normalizar_guid(jdl.client_guid),
            fazenda_nome=jdl.farm_name,
            fazenda_guid=normalizar_guid(jdl.farm_guid),
            talhao_nome=jdl.field_name,
            talhao_guid=normalizar_guid(jdl.field_guid),
            implemento_nome=impl.name if impl else None,
            implemento_largura_m=impl.width_m if impl else None,
            operacao="plantio" if "Plantio" in jdl.device_names else None,
        )
        return ParsedSession(jdl.sha256, ADAPTER, VERSAO, meta, amostras, diag)

    # --------------------------------------------------------------- internos
    @staticmethod
    def _colunas(jdl: JdlFile, diag: Diagnostico) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Séries brutas -> (t_ms, valor físico); 'não disponível' vira NaN."""
        out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for cid, s in jdl.series.items():
            c = jdl.channels[cid]
            col = ch.DDI_TO_COLUMN[c.ddi][0]
            raw = np.asarray(s.raw, dtype=np.int64)
            t = np.asarray(s.t_ms, dtype=np.float64)
            if col in out and len(t) <= len(out[col][0]):
                continue  # canal duplicado: fica o que tem mais amostras
            vals = raw / c.scale + c.offset
            na = raw <= ch.RAW_NA
            vals[na] = np.nan
            out[col] = (t, vals)
            diag.canais[col] = {
                "canal": cid,
                "ddi": c.ddi,
                "unidade": c.unit,
                "grupo": c.group,
                "escala": c.scale,
                "offset": c.offset,
                "amostras": len(raw),
                "nao_disponivel": int(na.sum()),
            }
        diag.canais_ausentes = [c for c in ch.ESSENCIAIS if c not in out]
        if diag.canais_ausentes and out:
            diag.avisos.append(f"canais ausentes: {', '.join(diag.canais_ausentes)}")
        return out

    def _reamostrar(
        self,
        colunas: dict[str, tuple[np.ndarray, np.ndarray]],
        jdl: JdlFile,
        t0: pd.Timestamp,
        diag: Diagnostico,
    ) -> pd.DataFrame:
        tempos = [t for t, _ in colunas.values() if len(t)]
        seg_min = int(math.floor(min(float(t.min()) for t in tempos) / 1000.0))
        seg_max = int(math.floor(max(float(t.max()) for t in tempos) / 1000.0))
        segundos = np.arange(seg_min, seg_max + 1)
        grade = pd.DataFrame(index=segundos)

        for col, (t, v) in colunas.items():
            seg = np.floor(t / 1000.0).astype(np.int64)
            serie = pd.Series(v, index=seg)
            if col in ch.COUNTER_COLUMNS:
                grade[col] = serie.groupby(level=0).last().reindex(segundos).ffill()
            else:
                media = serie.groupby(level=0).mean()
                grade[col] = media.reindex(segundos).ffill(limit=MAX_FILL_S)

        lat, lon = self._posicoes(jdl, segundos, diag)
        df = pd.DataFrame(index=segundos)
        df["ts"] = t0 + pd.to_timedelta(segundos, unit="s")
        df["lat"], df["lon"] = lat, lon
        df["gps_valid"] = np.isfinite(lat)
        for col in grade.columns:
            df[col] = grade[col]
        # O Gen4 não informa estado do motor: <NA>, a sanitização deriva.
        return no_schema_universal(df)

    @staticmethod
    def _posicoes(
        jdl: JdlFile, segundos: np.ndarray, diag: Diagnostico
    ) -> tuple[np.ndarray, np.ndarray]:
        n, base = len(segundos), int(segundos[0])
        lat, lon = np.full(n, np.nan), np.full(n, np.nan)
        g = jdl.gps
        if g.t_ms:
            t = np.asarray(g.t_ms)
            la, lo = np.asarray(g.lat), np.asarray(g.lon)
            ok = _gps_plausivel(la, lo)
            idx = np.floor(t[ok] / 1000.0).astype(np.int64) - base
            dentro = (idx >= 0) & (idx < n)
            if dentro.any():
                df = pd.DataFrame({"i": idx[dentro], "lat": la[ok][dentro], "lon": lo[ok][dentro]})
                media = df.groupby("i").mean()
                ii = media.index.to_numpy()
                lat[ii], lon[ii] = media["lat"].to_numpy(), media["lon"].to_numpy()
                diag.fonte_posicao = "trilha_gps"
                return lat, lon
        # Sem trilha: centro da caixa de cada bloco (precisão de dezenas de metros).
        usou = False
        for chunk in jdl.chunks:
            centro = chunk.centro
            if (
                centro is None
                or not _gps_plausivel(np.array([centro[0]]), np.array([centro[1]]))[0]
            ):
                continue
            i0 = int(math.floor(chunk.inicio_ms / 1000.0)) - base
            i1 = int(math.floor((chunk.inicio_ms + chunk.duration_ms) / 1000.0)) - base
            i0, i1 = max(i0, 0), min(i1, n - 1)
            if i1 >= i0:
                lat[i0 : i1 + 1], lon[i0 : i1 + 1] = centro
                usou = True
        if usou:
            diag.fonte_posicao = "caixa_do_bloco"
            diag.avisos.append("sem trilha GPS: posição aproximada pelo centro de cada bloco")
        return lat, lon
