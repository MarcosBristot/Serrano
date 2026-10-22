"""Casos de uso de alertas: ciclo de vida, configuração por organização, reprocessamento
e envio da outbox de notificações."""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from typing import Any, Protocol
from uuid import UUID

from sistemacampero.domain.alertas import AcaoAlerta, config_de
from sistemacampero.domain.ingestao import TipoJob
from sistemacampero.domain.ports import RepositorioIngestao
from sistemacampero.domain.services.rules import ConfigRegras, LinhasBase
from sistemacampero.domain.telemetry import MetadadosSessao

logger = logging.getLogger(__name__)


class RepositorioAlertas(Protocol):
    def config(self, org: UUID) -> dict[str, Any] | None: ...
    def salvar_config(
        self, org: UUID, versao: str, config: dict[str, Any], usuario: UUID | None
    ) -> None: ...
    def linhas_base(self, org: UUID, meta: MetadadosSessao, sha_atual: str) -> LinhasBase: ...
    def arquivos_processados(self, org: UUID) -> list[UUID]: ...
    def mudar_status(
        self, org: UUID, alerta_id: UUID, acao: AcaoAlerta, usuario_id: UUID | None
    ) -> dict[str, Any]: ...
    def reivindicar_notificacoes(self, limite: int) -> list[dict[str, Any]]: ...
    def dados_notificacao(
        self, org: UUID, alerta_id: UUID, destino_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...
    def marcar_notificacao(
        self, ident: UUID, ok: bool, erro: str | None, tentativas: int
    ) -> None: ...


class Enviador(Protocol):
    def enviar(self, alerta: dict[str, Any], destino: dict[str, Any]) -> None: ...


class ServicoAlertas:
    def __init__(self, repo: RepositorioAlertas, ingestao: RepositorioIngestao) -> None:
        self._repo = repo
        self._ingestao = ingestao

    def regras(self, org: UUID) -> ConfigRegras:
        return config_de(self._repo.config(org))

    def salvar_regras(self, org: UUID, dados: dict[str, Any], usuario: UUID | None) -> ConfigRegras:
        cfg = config_de(dados)
        self._repo.salvar_config(org, cfg.versao, asdict(cfg), usuario)
        return cfg

    def linhas_base(self, org: UUID, meta: MetadadosSessao, sha: str) -> LinhasBase:
        return self._repo.linhas_base(org, meta, sha)

    def mudar_status(
        self, org: UUID, alerta_id: UUID, acao: AcaoAlerta, usuario: UUID | None
    ) -> dict[str, Any]:
        return self._repo.mudar_status(org, alerta_id, acao, usuario)

    def reprocessar(self, org: UUID) -> int:
        """Refaz todas as sessões (do bruto) com a configuração atual de regras."""
        marca = uuid.uuid4().hex[:12]
        arquivos = self._repo.arquivos_processados(org)
        for a in arquivos:
            self._ingestao.enfileirar(
                org,
                TipoJob.PROCESSAR_ARQUIVO,
                {"arquivo_id": str(a), "motivo": "reanalise"},
                chave=f"reanalise:{marca}:{a}",
            )
        return len(arquivos)


class ServicoNotificacoes:
    def __init__(self, repo: RepositorioAlertas, enviador: Enviador) -> None:
        self._repo = repo
        self._enviador = enviador

    def enviar_pendentes(self, limite: int = 20) -> int:
        """Chamado pelo worker a cada volta do laço. Devolve quantas tentou."""
        itens = self._repo.reivindicar_notificacoes(limite)
        for n in itens:
            try:
                alerta, destino = self._repo.dados_notificacao(
                    n["organizacao_id"], n["alerta_id"], n["destino_id"]
                )
                self._enviador.enviar(alerta, destino)
                self._repo.marcar_notificacao(n["id"], True, None, n["tentativas"])
            except Exception as exc:
                logger.warning(
                    "notificação falhou",
                    extra={"notificacao": str(n["id"]), "erro": str(exc)[:200]},
                )
                self._repo.marcar_notificacao(
                    n["id"], False, f"{type(exc).__name__}: {exc}", n["tentativas"]
                )
        return len(itens)
