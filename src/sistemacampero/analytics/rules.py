"""Etapa 4: motor de regras (IA baseada em regras do MVP) sobre o dado LIMPO.

Cada regra devolve ``Alert``. Os limiares ficam em ``RuleConfig`` e a versão da
configuração é gravada junto com os resultados, para reprocessar sem tocar no bruto.

Diferença em relação ao protótipo: o John Deere Gen4 não informa nível de tanque, então
a regra "queda de combustível" foi substituída por (a) divergência entre a vazão integrada
e o contador acumulado do motor e (b) vazão fora do padrão do próprio trator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from sistemacampero.processing.metrics import haversine_m
from sistemacampero.schema.universal import ParsedSession


@dataclass(frozen=True)
class RuleConfig:
    idle_min_minutes: float = 20.0         # motor ligado e parado por mais que isso
    idle_gap_tolerance_s: int = 30         # junta ociosidades separadas por pausas curtas
    fuel_dev_threshold: float = 0.30       # 30% acima do baseline (igual ao protótipo)
    fuel_window_min: int = 10              # janela de mediana para vazão em trabalho
    fuel_min_window_samples: int = 120
    counter_mismatch_ratio: float = 0.15   # |contador - integral| / contador
    counter_min_liters: float = 5.0
    gps_max_speed_kmh: float = 40.0
    gps_gap_m: float = 200.0               # salto entre fim de um bloco e início do próximo
    no_gps_min_engine_h: float = 0.25
    l_ha_dev_threshold: float = 0.30
    l_ha_min_sessions: int = 5             # amostras mínimas p/ formar baseline

    @property
    def version(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha1(blob).hexdigest()[:10]


@dataclass
class Alert:
    kind: str                # ociosidade | vazao_alta | contador_divergente | gps_salto | sem_gps | l_ha_alto
    severity: str            # info | atencao | alto
    source_sha256: str
    machine_serial: str
    start_utc: pd.Timestamp | None
    end_utc: pd.Timestamp | None
    value: float | None
    message: str
    field_name: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _runs(mask: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """Trechos contíguos de True, unindo pausas de até ``gap`` amostras."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    runs, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap + 1:
            runs.append((start, prev))
            start = i
        prev = i
    runs.append((start, prev))
    return runs


def _base(session: ParsedSession, **kw) -> dict:
    return dict(
        source_sha256=session.source_sha256,
        machine_serial=session.machine.serial,
        field_name=session.context.field_name,
        **kw,
    )


# ------------------------------------------------------------------- regras por sessão
def detect_idle(session: ParsedSession, df: pd.DataFrame, cfg: RuleConfig) -> list[Alert]:
    idle = (df["engine_on"] & (df["speed_kmh"] < 1.0)).to_numpy()
    out = []
    for a, b in _runs(idle, cfg.idle_gap_tolerance_s):
        minutes = (b - a + 1) / 60.0
        if minutes < cfg.idle_min_minutes:
            continue
        liters = float(df["fuel_rate_lph"].iloc[a : b + 1].fillna(0).sum()) / 3600.0
        out.append(Alert(
            kind="ociosidade",
            severity="alto" if minutes >= 3 * cfg.idle_min_minutes else "atencao",
            start_utc=df["ts"].iloc[a], end_utc=df["ts"].iloc[b], value=round(minutes, 1),
            message=f"Motor ligado e parado por {minutes:.0f} min (~{liters:.1f} L gastos).",
            details={"litros": round(liters, 2)},
            **_base(session),
        ))
    return out


def detect_high_fuel_rate(
    session: ParsedSession, df: pd.DataFrame, cfg: RuleConfig, baseline_lph: float | None
) -> list[Alert]:
    """Vazão em trabalho muito acima do padrão do próprio trator (baseline do histórico)."""
    if not baseline_lph:
        return []
    work = df["engine_on"] & (df["speed_kmh"] >= 1.0)
    rate = df["fuel_rate_lph"].where(work)
    win = cfg.fuel_window_min * 60
    med = rate.rolling(win, min_periods=cfg.fuel_min_window_samples).median()
    over = (med > baseline_lph * (1 + cfg.fuel_dev_threshold)).to_numpy()
    out = []
    for a, b in _runs(over, 60):
        if (b - a + 1) < win:
            continue
        v = float(med.iloc[a : b + 1].median())
        out.append(Alert(
            kind="vazao_alta", severity="atencao",
            start_utc=df["ts"].iloc[a], end_utc=df["ts"].iloc[b], value=round(v, 1),
            message=(f"Vazão de {v:.1f} L/h por {(b - a + 1) / 60:.0f} min, "
                     f"{100 * (v / baseline_lph - 1):.0f}% acima do padrão do trator ({baseline_lph:.1f} L/h)."),
            details={"baseline_lph": round(baseline_lph, 2)},
            **_base(session),
        ))
    return out


def detect_counter_mismatch(session: ParsedSession, m, cfg: RuleConfig) -> list[Alert]:
    c, i = m.fuel_counter_l, m.fuel_integral_l
    if c is None or i is None or pd.isna(c) or pd.isna(i) or c < cfg.counter_min_liters:
        return []
    ratio = abs(c - i) / c
    if ratio <= cfg.counter_mismatch_ratio:
        return []
    return [Alert(
        kind="contador_divergente", severity="info",
        start_utc=m.start_utc, end_utc=m.end_utc, value=round(100 * ratio, 1),
        message=(f"Contador de combustível ({c:.1f} L) diverge {100 * ratio:.0f}% da vazão "
                 f"integrada ({i:.1f} L). Verificar lacunas de dados ou sensor."),
        details={"contador_l": round(c, 2), "integral_l": round(i, 2)},
        **_base(session),
    )]


def detect_gps_jumps(session: ParsedSession, cfg: RuleConfig) -> list[Alert]:
    out, clock, prev_end = [], 0.0, None
    t0 = pd.Timestamp(session.started_at)
    for dur, a, b in session.gps_chunks:
        t = t0 + pd.to_timedelta(clock, unit="ms")
        if a and b and dur > 0:
            v = haversine_m(a, b) / (dur / 1000.0) * 3.6
            if v > cfg.gps_max_speed_kmh:
                out.append(Alert(kind="gps_salto", severity="info", start_utc=t, end_utc=None,
                                 value=round(v, 1),
                                 message=f"Posição GPS implica {v:.0f} km/h em 30 s (salto impossível).",
                                 **_base(session)))
            if prev_end and haversine_m(prev_end, a) > cfg.gps_gap_m:
                out.append(Alert(kind="gps_salto", severity="info", start_utc=t, end_utc=None,
                                 value=round(haversine_m(prev_end, a), 0),
                                 message="Descontinuidade de posição entre blocos consecutivos.",
                                 **_base(session)))
        prev_end = b
        clock += dur
    return out


def detect_no_gps(session: ParsedSession, m, cfg: RuleConfig) -> list[Alert]:
    if m.engine_on_h >= cfg.no_gps_min_engine_h and m.gps_coverage == 0:
        return [Alert(
            kind="sem_gps", severity="info", start_utc=m.start_utc, end_utc=m.end_utc,
            value=round(m.engine_on_h, 2),
            message=f"{m.engine_on_h:.1f} h de motor ligado sem nenhum ponto de GPS: sem talhão/área.",
            **_base(session),
        )]
    return []


# --------------------------------------------------------------- regra entre sessões
def detect_l_per_ha_outliers(sessions: pd.DataFrame, cfg: RuleConfig) -> list[Alert]:
    """L/ha acima do baseline (mediana) do mesmo trator + operação + implemento."""
    out = []
    s = sessions.dropna(subset=["l_per_ha"])
    for (serial, op, impl), g in s.groupby(["machine_serial", "operation", "implement_name"], dropna=False):
        if len(g) < cfg.l_ha_min_sessions:
            continue
        base = float(g["l_per_ha"].median())
        for _, r in g[g["l_per_ha"] > base * (1 + cfg.l_ha_dev_threshold)].iterrows():
            out.append(Alert(
                kind="l_ha_alto", severity="atencao", source_sha256=r.source_sha256,
                machine_serial=serial, start_utc=r.start_utc, end_utc=r.end_utc,
                value=round(float(r.l_per_ha), 2), field_name=r.field_name,
                message=(f"Consumo de {r.l_per_ha:.1f} L/ha, "
                         f"{int(cfg.l_ha_dev_threshold * 100)}% acima do baseline ({base:.1f} L/ha)."),
                details={"baseline_l_ha": round(base, 2), "implemento": impl},
            ))
    return out
