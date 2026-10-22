"""Caso de uso: um arquivo bruto -> sessão limpa, métricas, qualidade e alertas.

Sem I/O: quem chama entrega os bytes e decide o que persistir (worker no M3, CLI e
script de regressão hoje).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

import pandas as pd

from sistemacampero.domain.ports import RegistroDeAdapters
from sistemacampero.domain.services import rules
from sistemacampero.domain.services.coverage import Cobertura, calcular_cobertura
from sistemacampero.domain.services.geo import Localizacao, LocalizadorDeTalhoes
from sistemacampero.domain.services.metrics import MetricasSessao, calcular_metricas
from sistemacampero.domain.services.quality import Qualidade, avaliar
from sistemacampero.domain.services.sanitization import SANITIZER_VERSION, sanitizar
from sistemacampero.domain.telemetry import (
    EmptyFile,
    MetadadosSessao,
    ParseContext,
    ParsedSession,
)

BuscaLinhasBase = Callable[[MetadadosSessao], rules.LinhasBase]


@dataclass(slots=True)
class ResultadoSessao:
    sessao: ParsedSession
    limpo: pd.DataFrame
    sanitizacao: dict[str, int]
    sanitizador_versao: str
    metricas: MetricasSessao | None
    qualidade: Qualidade
    alertas: list[rules.Alerta] = field(default_factory=list)
    localizacao: Localizacao | None = None  # talhão por GPS (None = sem contornos)
    talhao_id: UUID | None = None  # o usado no recorte da cobertura (manual > GPS)
    cobertura: Cobertura | None = None
    regras: rules.ConfigRegras = field(default_factory=rules.ConfigRegras)


class ProcessadorDeArquivo:
    def __init__(
        self, adapters: RegistroDeAdapters, regras: rules.ConfigRegras | None = None
    ) -> None:
        self._adapters = adapters
        self._regras = regras or rules.ConfigRegras()

    def processar(
        self,
        dados: bytes,
        ctx: ParseContext,
        linha_base_vazao_lph: float | None = None,
        talhoes: LocalizadorDeTalhoes | None = None,
        talhao_manual_id: UUID | None = None,
        regras: rules.ConfigRegras | None = None,
        linhas_base: BuscaLinhasBase | None = None,
    ) -> ResultadoSessao | EmptyFile:
        adapter = self._adapters.escolher(dados[:64], ctx)
        lido = adapter.parse(io.BytesIO(dados), ctx)
        if isinstance(lido, EmptyFile):
            return lido

        limpo, relatorio = sanitizar(lido.amostras)
        largura = lido.metadados.implemento_largura_m

        localizacao = None
        if talhoes is not None and not talhoes.vazio:
            trabalho = limpo["engine_on"].astype(bool) & (limpo["speed_kmh"] >= 1.0)
            localizacao = talhoes.localizar(
                limpo["lat"].to_numpy(), limpo["lon"].to_numpy(), trabalho.to_numpy()
            )
        talhao_id = talhao_manual_id or (localizacao.talhao_id if localizacao else None)
        contorno = talhoes.contorno(talhao_id) if talhoes is not None and talhao_id else None
        cobertura = calcular_cobertura(limpo, largura, contorno)
        metricas = calcular_metricas(
            limpo,
            largura,
            cobertura.area_ha if cobertura else None,
            cobertura.sobreposicao_pct if cobertura else None,
        )
        qualidade = avaliar(
            limpo,
            metricas,
            relatorio,
            lido.diagnostico.canais_ausentes,
            localizacao.confianca if localizacao and localizacao.talhao_id else None,
        )
        if cobertura is not None and cobertura.dentro_do_talhao_ha is not None:
            qualidade.detalhes["dentro_do_talhao_ha"] = round(cobertura.dentro_do_talhao_ha, 3)
        cfg, chave = regras or self._regras, lido.sha256
        base = linhas_base(lido.metadados) if linhas_base else rules.LinhasBase()
        if linha_base_vazao_lph is not None:
            base = rules.LinhasBase(linha_base_vazao_lph, base.l_ha, base.sessoes)
        meta = lido.metadados
        alertas = [
            *rules.ociosidade(chave, limpo, cfg),
            *rules.vazao_alta(chave, limpo, cfg, base.vazao_lph),
            *rules.l_ha_acima(
                chave, metricas.l_ha if metricas else None, base, cfg, meta.inicio, meta.fim
            ),
            *rules.gps_salto(chave, limpo, cfg),
            *rules.de_qualidade(chave, qualidade, lido.metadados.inicio, lido.metadados.fim),
        ]
        return ResultadoSessao(
            sessao=lido,
            limpo=limpo,
            sanitizacao=relatorio,
            sanitizador_versao=SANITIZER_VERSION,
            metricas=metricas,
            qualidade=qualidade,
            alertas=alertas,
            localizacao=localizacao,
            talhao_id=talhao_id,
            cobertura=cobertura,
            regras=cfg,
        )
