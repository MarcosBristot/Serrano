"""Regras de alerta sobre o dado LIMPO (base do motor de regras do M6).

Os limiares ficam em ``ConfigRegras``; a versão (hash da config) vai junto com cada
alerta, para reprocessar sem tocar no bruto. Nenhuma regra dispara com NaN.

Mudanças em relação ao código de referência:
* ``gps_salto`` usa a velocidade implícita entre posições consecutivas (distância / tempo
  decorrido), não a distância entre "fim" e "início" de blocos: esses pontos são cantos de
  uma caixa, e 165 de 169 alertas eram falsos (defeito 3);
* ``contador_divergente`` vem da checagem de qualidade, que exige volume E duração
  mínimos (defeito 2);
* inconsistências de dado (horímetro x motor) viram alerta ``qualidade_dado``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from sistemacampero.domain.services.geo import distancias_m
from sistemacampero.domain.services.metrics import VELOCIDADE_TRABALHO_KMH
from sistemacampero.domain.services.quality import Qualidade

VERSAO_REGRAS = "2"


@dataclass(frozen=True)
class ConfigRegras:
    ociosidade_min_minutos: float = 20.0
    ociosidade_tolerancia_s: int = 30  # junta ociosidades separadas por pausas curtas
    vazao_desvio: float = 0.30  # 30% acima da linha de base
    vazao_janela_min: int = 10
    vazao_min_amostras: int = 120
    gps_velocidade_max_kmh: float = 40.0
    gps_salto_min_m: float = 50.0  # ignora tremulação do receptor
    l_ha_desvio: float = 0.30
    l_ha_min_sessoes: int = 5

    @property
    def hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]

    @property
    def versao(self) -> str:
        return f"{VERSAO_REGRAS}+{self.hash}"


@dataclass(frozen=True, slots=True)
class Alerta:
    tipo: str
    severidade: str  # info | atencao | alto
    chave_sessao: str  # sha256 do bruto
    mensagem: str
    inicio: datetime | None = None
    fim: datetime | None = None
    valor: float | None = None
    limiar: float | None = None
    detalhes: dict[str, Any] = field(default_factory=dict)

    @property
    def impressao_digital(self) -> str:
        """Mesmo evento => mesma impressão: o reprocessamento não duplica alertas."""
        inicio = self.inicio.isoformat() if self.inicio else "-"
        return hashlib.sha256(f"{self.tipo}|{self.chave_sessao}|{inicio}".encode()).hexdigest()[:32]


def _trechos(mascara: np.ndarray, tolerancia: int) -> list[tuple[int, int]]:
    """Trechos contíguos de True, unindo pausas de até ``tolerancia`` amostras."""
    idx = np.flatnonzero(mascara)
    if not len(idx):
        return []
    trechos, inicio, anterior = [], int(idx[0]), int(idx[0])
    for i in idx[1:]:
        if i - anterior > tolerancia + 1:
            trechos.append((inicio, anterior))
            inicio = int(i)
        anterior = int(i)
    trechos.append((inicio, anterior))
    return trechos


def _ts(df: pd.DataFrame, i: int) -> datetime:
    valor: datetime = df["ts"].iloc[i].to_pydatetime()
    return valor


# ------------------------------------------------------------------- por sessão
def ociosidade(chave: str, df: pd.DataFrame, cfg: ConfigRegras) -> list[Alerta]:
    parado = (df["engine_on"].astype(bool) & (df["speed_kmh"] < VELOCIDADE_TRABALHO_KMH)).to_numpy()
    out = []
    for a, b in _trechos(parado, cfg.ociosidade_tolerancia_s):
        minutos = (b - a + 1) / 60.0
        if minutos < cfg.ociosidade_min_minutos:
            continue
        litros = float(df["fuel_rate_lph"].iloc[a : b + 1].fillna(0).sum()) / 3600.0
        out.append(
            Alerta(
                tipo="ociosidade",
                severidade="alto" if minutos >= 3 * cfg.ociosidade_min_minutos else "atencao",
                chave_sessao=chave,
                inicio=_ts(df, a),
                fim=_ts(df, b),
                valor=round(minutos, 1),
                limiar=cfg.ociosidade_min_minutos,
                mensagem=f"Motor ligado e parado por {minutos:.0f} min (~{litros:.1f} L gastos).",
                detalhes={"litros": round(litros, 2)},
            )
        )
    return out


def vazao_alta(
    chave: str, df: pd.DataFrame, cfg: ConfigRegras, linha_base_lph: float | None
) -> list[Alerta]:
    """Vazão em trabalho acima da linha de base da mesma máquina+implemento+operação."""
    if linha_base_lph is None or not np.isfinite(linha_base_lph) or linha_base_lph <= 0:
        return []
    trabalhando = df["engine_on"].astype(bool) & (df["speed_kmh"] >= VELOCIDADE_TRABALHO_KMH)
    janela = cfg.vazao_janela_min * 60
    mediana = (
        df["fuel_rate_lph"]
        .where(trabalhando)
        .rolling(janela, min_periods=cfg.vazao_min_amostras)
        .median()
    )
    limiar = linha_base_lph * (1 + cfg.vazao_desvio)
    acima = (mediana > limiar).to_numpy()
    out = []
    for a, b in _trechos(acima, 60):
        if (b - a + 1) < janela:
            continue
        v = float(mediana.iloc[a : b + 1].median())
        out.append(
            Alerta(
                tipo="vazao_alta",
                severidade="atencao",
                chave_sessao=chave,
                inicio=_ts(df, a),
                fim=_ts(df, b),
                valor=round(v, 1),
                limiar=round(limiar, 2),
                mensagem=(
                    f"Vazão de {v:.1f} L/h por {(b - a + 1) / 60:.0f} min, "
                    f"{100 * (v / linha_base_lph - 1):.0f}% acima da linha de base "
                    f"({linha_base_lph:.1f} L/h)."
                ),
                detalhes={"linha_base_lph": round(linha_base_lph, 2)},
            )
        )
    return out


def gps_salto(chave: str, df: pd.DataFrame, cfg: ConfigRegras) -> list[Alerta]:
    """Posições que exigiriam velocidade impossível (salto de GPS).

    Compara cada posição DISTINTA com a anterior, pelo tempo decorrido entre elas:
    posição repetida (ex.: centro da caixa de um bloco de 30 s) não é "parado e depois
    teleportado". Saltos em segundos consecutivos viram um alerta só.
    """
    pos = df.loc[df["gps_valid"] & df["lat"].notna() & df["lon"].notna(), ["ts", "lat", "lon"]]
    if len(pos) < 2:
        return []
    lat, lon = pos["lat"].to_numpy(), pos["lon"].to_numpy()
    mudou = np.r_[True, (np.diff(lat) != 0) | (np.diff(lon) != 0)]
    pos = pos[mudou]
    if len(pos) < 2:
        return []
    lat, lon = pos["lat"].to_numpy(), pos["lon"].to_numpy()
    ts = pos["ts"].to_numpy()
    dist = distancias_m(lat, lon)
    dt_s = np.diff(ts).astype("timedelta64[ms]").astype(np.float64) / 1000.0
    velocidade = dist / np.maximum(dt_s, 1e-3) * 3.6
    salto = (velocidade > cfg.gps_velocidade_max_kmh) & (dist > cfg.gps_salto_min_m)
    out = []
    for a, b in _trechos(salto, 0):
        d = float(distancias_m(lat[[a, b + 1]], lon[[a, b + 1]])[0])
        intervalo = float(dt_s[a : b + 1].sum())
        v = d / max(intervalo, 1e-3) * 3.6
        out.append(
            Alerta(
                tipo="gps_salto",
                severidade="info",
                chave_sessao=chave,
                inicio=pos["ts"].iloc[a].to_pydatetime(),
                fim=pos["ts"].iloc[b + 1].to_pydatetime(),
                valor=round(v, 1),
                limiar=cfg.gps_velocidade_max_kmh,
                mensagem=(
                    f"Posição saltou {d:.0f} m em {intervalo:.0f} s ({v:.0f} km/h implícitos)."
                ),
                detalhes={"distancia_m": round(d, 1), "intervalo_s": intervalo},
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class LinhasBase:
    """Medianas do histórico da mesma máquina + implemento + operação (None = histórico curto)."""

    vazao_lph: float | None = None
    l_ha: float | None = None
    sessoes: int = 0


def l_ha_acima(
    chave: str,
    l_ha: float | None,
    base: LinhasBase,
    cfg: ConfigRegras,
    inicio: datetime,
    fim: datetime,
) -> list[Alerta]:
    """L/ha da sessão acima da mediana do histórico da mesma combinação."""
    if l_ha is None or base.l_ha is None or base.sessoes < cfg.l_ha_min_sessoes:
        return []
    if not (np.isfinite(l_ha) and np.isfinite(base.l_ha)) or base.l_ha <= 0:
        return []
    limiar = base.l_ha * (1 + cfg.l_ha_desvio)
    if l_ha <= limiar:
        return []
    return [
        Alerta(
            tipo="l_ha_alto",
            severidade="atencao",
            chave_sessao=chave,
            inicio=inicio,
            fim=fim,
            valor=round(l_ha, 2),
            limiar=round(limiar, 2),
            mensagem=(
                f"Consumo de {l_ha:.1f} L/ha, {100 * (l_ha / base.l_ha - 1):.0f}% acima da "
                f"mediana de {base.sessoes} sessões desta máquina e implemento "
                f"({base.l_ha:.1f} L/ha)."
            ),
            detalhes={"linha_base_l_ha": round(base.l_ha, 2), "sessoes_base": base.sessoes},
        )
    ]


def de_qualidade(chave: str, qualidade: Qualidade, inicio: datetime, fim: datetime) -> list[Alerta]:
    """Problemas de dado relevantes viram alerta (o gestor precisa saber)."""
    tipos = {
        "CONTADOR_DIVERGE": "contador_divergente",
        "HORIMETRO_DIVERGE": "qualidade_dado",
        "SEM_GPS": "sem_gps",
    }
    return [
        Alerta(
            tipo=tipos[p.codigo],
            severidade=p.severidade,
            chave_sessao=chave,
            inicio=inicio,
            fim=fim,
            valor=p.valor,
            mensagem=p.mensagem,
            detalhes={"codigo": p.codigo, "qualidade_score": qualidade.score},
        )
        for p in qualidade.problemas
        if p.codigo in tipos
    ]


# ------------------------------------------------------------------- entre sessões
@dataclass(frozen=True, slots=True)
class ResumoSessao:
    chave_sessao: str
    combinacao: tuple[str | None, str | None, str | None]  # máquina, implemento, operação
    l_ha: float | None
    inicio: datetime
    fim: datetime


def l_ha_alto(sessoes: Iterable[ResumoSessao], cfg: ConfigRegras) -> list[Alerta]:
    """L/ha acima da mediana da mesma combinação máquina+implemento+operação."""
    grupos: dict[tuple[str | None, str | None, str | None], list[ResumoSessao]] = {}
    for s in sessoes:
        if s.l_ha is not None and np.isfinite(s.l_ha):
            grupos.setdefault(s.combinacao, []).append(s)
    out = []
    for combinacao, grupo in grupos.items():
        if len(grupo) < cfg.l_ha_min_sessoes:
            continue
        base = float(np.median([s.l_ha for s in grupo if s.l_ha is not None]))
        limiar = base * (1 + cfg.l_ha_desvio)
        for s in grupo:
            if s.l_ha is not None and s.l_ha > limiar:
                out.append(
                    Alerta(
                        tipo="l_ha_alto",
                        severidade="atencao",
                        chave_sessao=s.chave_sessao,
                        inicio=s.inicio,
                        fim=s.fim,
                        valor=round(s.l_ha, 2),
                        limiar=round(limiar, 2),
                        mensagem=(
                            f"Consumo de {s.l_ha:.1f} L/ha, acima da linha de base "
                            f"({base:.1f} L/ha) desta máquina e implemento."
                        ),
                        detalhes={"linha_base_l_ha": round(base, 2), "combinacao": combinacao},
                    )
                )
    return out
