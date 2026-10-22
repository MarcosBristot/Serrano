"""Caso de uso: um arquivo bruto -> sessão limpa, métricas, qualidade e alertas.

Sem I/O: quem chama entrega os bytes e decide o que persistir (worker no M3, CLI e
script de regressão hoje).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from sistemacampero.domain.ports import RegistroDeAdapters
from sistemacampero.domain.services import rules
from sistemacampero.domain.services.metrics import MetricasSessao, calcular_metricas
from sistemacampero.domain.services.quality import Qualidade, avaliar
from sistemacampero.domain.services.sanitization import SANITIZER_VERSION, sanitizar
from sistemacampero.domain.telemetry import EmptyFile, ParseContext, ParsedSession


@dataclass(slots=True)
class ResultadoSessao:
    sessao: ParsedSession
    limpo: pd.DataFrame
    sanitizacao: dict[str, int]
    sanitizador_versao: str
    metricas: MetricasSessao | None
    qualidade: Qualidade
    alertas: list[rules.Alerta] = field(default_factory=list)


class ProcessadorDeArquivo:
    def __init__(
        self, adapters: RegistroDeAdapters, regras: rules.ConfigRegras | None = None
    ) -> None:
        self._adapters = adapters
        self._regras = regras or rules.ConfigRegras()

    def processar(
        self, dados: bytes, ctx: ParseContext, linha_base_vazao_lph: float | None = None
    ) -> ResultadoSessao | EmptyFile:
        adapter = self._adapters.escolher(dados[:64], ctx)
        lido = adapter.parse(io.BytesIO(dados), ctx)
        if isinstance(lido, EmptyFile):
            return lido

        limpo, relatorio = sanitizar(lido.amostras)
        metricas = calcular_metricas(limpo, lido.metadados.implemento_largura_m)
        qualidade = avaliar(limpo, metricas, relatorio, lido.diagnostico.canais_ausentes)
        cfg, chave = self._regras, lido.sha256
        alertas = [
            *rules.ociosidade(chave, limpo, cfg),
            *rules.vazao_alta(chave, limpo, cfg, linha_base_vazao_lph),
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
        )
