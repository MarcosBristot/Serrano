"""Resumo da semana em poucas linhas, no jeito do WhatsApp, com a ação mais importante.

O produtor não abre painel toda semana: o resumo chega até ele (e-mail ou webhook hoje; o texto
já sai pronto para WhatsApp). Uma vez por semana, segunda a partir das 7 h no fuso da fazenda.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from sistemacampero.application.kpis import Filtros, ServicoKpis
from sistemacampero.application.manutencao import ServicoManutencao

logger = logging.getLogger(__name__)

_PIN_JD = re.compile(r"^1[A-Z]{2}(\d{4}[A-Z])")
HORA_ENVIO = 7  # segunda-feira, hora local
LIMIAR_OCIOSIDADE_PCT = 20.0


class RepositorioResumo(Protocol):
    def orgs_com_destino(self) -> list[dict[str, Any]]: ...
    def ja_enviado(self, org: UUID, semana: str) -> bool: ...
    def registrar(self, org: UUID, semana: str, destinos: int, texto: str) -> None: ...
    def destinos(self, org: UUID) -> list[dict[str, Any]]: ...
    def nome_org(self, org: UUID) -> str: ...


class EnviadorResumo(Protocol):
    def resumo(self, destino: dict[str, Any], titulo: str, texto: str) -> None: ...


def _n(v: float | None, casas: int = 0) -> str:
    if v is None:
        return "—"
    texto = f"{v:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _rs(v: float | None) -> str:
    return "—" if v is None else f"R$ {_n(v, 0)}"


def _maquina(m: dict[str, Any]) -> str:
    if m.get("apelido"):
        return str(m["apelido"])
    tipo = {"colheitadeira": "Colheitadeira", "pulverizador": "Pulverizador"}.get(
        m.get("tipo") or "", "Trator"
    )
    # PIN John Deere de trator: 1 + fábrica (2) + modelo ("1BM6210M..." = 6210M)
    pin = _PIN_JD.match(str(m["serial"]))
    modelo = m.get("modelo") or (pin.group(1) if pin else None)
    return f"{tipo} {modelo}" if modelo else f"{tipo} …{str(m['serial'])[-6:]}"


class ServicoResumoSemanal:
    def __init__(
        self,
        repo: RepositorioResumo,
        kpis: ServicoKpis,
        manutencao: ServicoManutencao,
        enviador: EnviadorResumo | None,
        frontend_url: str | None,
    ) -> None:
        self._repo = repo
        self._kpis = kpis
        self._manutencao = manutencao
        self._enviador = enviador
        self._url = (frontend_url or "").rstrip("/")

    def montar(self, org: UUID, fim: date | None = None) -> dict[str, Any]:
        """Os 7 dias até ``fim`` (ontem, por padrão): números, a ação da semana e o texto."""
        fim = fim or date.today() - timedelta(days=1)
        inicio = fim - timedelta(days=6)
        r = self._kpis.resumo(org, Filtros(inicio=inicio, fim=fim))
        frota = self._kpis.maquinas(org, {"inicio": inicio, "fim": fim})
        pendencias = self._manutencao.pendencias(org)
        sacas = sum((m["massa_kg"] or 0) for m in frota) / 60

        acoes: list[str] = []
        for p in pendencias[:2]:
            nome = next((_maquina(m) for m in frota if m["id"] == p["maquina_id"]), None)
            nome = nome or _maquina(p)
            if p["situacao"] == "vencida":
                acoes.append(
                    f"🔧 {nome}: {p['nome'].lower()} vencida (passou {_n(-p['faltam_h'])} h)."
                )
            else:
                quando = (
                    f"em ~{_n(max(1, p['dias_trabalho']))} dias de trabalho"
                    if p["dias_trabalho"] is not None
                    else f"em {_n(p['faltam_h'])} h"
                )
                acoes.append(f"🔧 {nome}: {p['nome'].lower()} {quando}. Agende.")
        for m in frota:
            if (m["ociosidade_pct"] or 0) >= LIMIAR_OCIOSIDADE_PCT and m["motor_h"] >= 2:
                acoes.append(
                    f"⏱️ {_maquina(m)} ficou {_n(m['ociosidade_pct'])}% parada com motor ligado"
                    f" ({_rs(m['custo_ocioso_rs'])} de diesel)."
                )

        nome = self._repo.nome_org(org)
        linhas = [f"🌾 *Serrano · {nome}*", f"Semana de {inicio:%d/%m} a {fim:%d/%m}", ""]
        if r["motor_h"] < 0.1:
            linhas.append(
                "Nenhuma operação registrada. Se as máquinas trabalharam, envie o pendrive."
            )
        else:
            linhas.append(
                f"🚜 {_n(r['trabalho_h'])} h trabalhando · ⛽ {_n(r['litros'])} L"
                f" ({_rs(r['custo_rs'])}) · 📐 {_n(r['area_ha'])} ha"
            )
            if sacas >= 1:
                linhas.append(f"🌾 Colhido: {_n(sacas)} sacas")
        if acoes:
            linhas += ["", "👉 *Para esta semana:*", *acoes[:3]]
        else:
            linhas += ["", "✅ Nada fora do normal. Bom trabalho!"]
        if self._url:
            linhas += ["", f"Ver no painel: {self._url}/"]
        return {
            "inicio": inicio,
            "fim": fim,
            "texto": "\n".join(linhas),
            "acoes": acoes,
            "trabalho_h": r["trabalho_h"],
            "litros": r["litros"],
            "custo_rs": r["custo_rs"],
            "area_ha": r["area_ha"],
            "sacas": sacas,
        }

    def enviar_da_semana(self, agora: datetime | None = None) -> int:
        """Worker: manda o resumo das fazendas com destino ativo (segunda, a partir das 7 h)."""
        if self._enviador is None:
            return 0
        enviados = 0
        for o in self._repo.orgs_com_destino():
            local = (agora or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo(o["fuso"]))
            if local.weekday() != 0 or local.hour < HORA_ENVIO:
                continue
            ano, semana, _ = local.isocalendar()
            chave = f"{ano}-W{semana:02d}"
            org = o["organizacao_id"]
            if self._repo.ja_enviado(org, chave):
                continue
            resumo = self.montar(org, local.date() - timedelta(days=1))
            ok = 0
            for d in self._repo.destinos(org):
                if not d["ativo"] or d["tipo"] not in ("email", "webhook"):
                    continue
                try:
                    self._enviador.resumo(d, "Resumo da semana", resumo["texto"])
                    ok += 1
                except Exception:  # um destino com problema não segura os outros
                    logger.warning("resumo semanal não enviado", extra={"destino": str(d["id"])})
            self._repo.registrar(org, chave, ok, resumo["texto"])
            enviados += 1
        return enviados
