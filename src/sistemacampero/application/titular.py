"""Direitos do titular: portabilidade e exclusão da conta com carência (LGPD art. 18)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sistemacampero.domain.errors import Conflito, Invalido
from sistemacampero.domain.tenancy import Principal

logger = logging.getLogger(__name__)

CONFIRMACAO = "EXCLUIR"


class RepoTitular(Protocol):
    def dados(self, usuario_id: UUID) -> dict[str, Any]: ...
    def impacto(self, usuario_id: UUID) -> list[dict[str, Any]]: ...
    def pedido_ativo(self, usuario_id: UUID) -> dict[str, Any] | None: ...
    def agendar(
        self, usuario_id: UUID, email: str | None, organizacoes: list[UUID], quando: datetime
    ) -> dict[str, Any]: ...
    def cancelar(self, usuario_id: UUID) -> bool: ...
    def vencidas(self, limite: int = 20) -> list[dict[str, Any]]: ...
    def excluir_organizacao(self, organizacao_id: UUID) -> list[tuple[str, str]]: ...
    def excluir_titular(self, usuario_id: UUID, email: str | None) -> None: ...
    def concluir(self, pedido_id: UUID, erro: str | None = None) -> None: ...


class Apagador(Protocol):
    def apagar(self, bucket: str, caminho: str) -> None: ...


def classificar(linha: dict[str, Any]) -> str:
    """O que acontece com a organização: 'excluida', 'sai' ou 'bloqueia' (precisa transferir)."""
    if linha["outros_membros"] == 0:
        return "excluida"
    if linha["papel"] == "owner" and linha["outros_donos"] == 0:
        return "bloqueia"
    return "sai"


class ServicoTitular:
    def __init__(self, repo: RepoTitular, storage: Apagador, carencia_dias: int = 7) -> None:
        self._repo = repo
        self._storage = storage
        self._carencia = timedelta(days=carencia_dias)

    def exportar(self, quem: Principal) -> dict[str, Any]:
        return self._repo.dados(quem.usuario_id)

    def situacao(self, quem: Principal) -> dict[str, Any]:
        impacto = [{**i, "acao": classificar(i)} for i in self._repo.impacto(quem.usuario_id)]
        return {
            "pedido": self._repo.pedido_ativo(quem.usuario_id),
            "organizacoes": impacto,
            "carencia_dias": self._carencia.days,
        }

    def solicitar_exclusao(self, quem: Principal, confirmacao: str) -> dict[str, Any]:
        if confirmacao.strip().upper() != CONFIRMACAO:
            raise Invalido(f'Digite "{CONFIRMACAO}" para confirmar.', codigo="CONFIRMACAO_INVALIDA")
        impacto = self._repo.impacto(quem.usuario_id)
        bloqueios = [i["nome"] for i in impacto if classificar(i) == "bloqueia"]
        if bloqueios:
            raise Conflito(
                "Você é o único dono de organizações com outros membros: "
                + ", ".join(bloqueios)
                + ". Torne outra pessoa dona ou remova os membros antes de excluir a conta.",
                codigo="TRANSFIRA_A_PROPRIEDADE",
            )
        sozinho = [i["organizacao_id"] for i in impacto if classificar(i) == "excluida"]
        quando = datetime.now(UTC) + self._carencia
        return self._repo.agendar(quem.usuario_id, quem.email, sozinho, quando)

    def cancelar(self, quem: Principal) -> bool:
        return self._repo.cancelar(quem.usuario_id)

    def executar_vencidas(self) -> int:
        """Worker: executa os pedidos cuja carência terminou. Devolve quantos concluiu."""
        feitos = 0
        for pedido in self._repo.vencidas():
            try:
                # Reconfere: se alguém entrou na organização durante a carência, ela fica.
                atual = {i["organizacao_id"]: i for i in self._repo.impacto(pedido["usuario_id"])}
                for org in pedido["organizacoes"]:
                    if org in atual and classificar(atual[org]) != "excluida":
                        continue
                    for bucket, caminho in self._repo.excluir_organizacao(org):
                        try:
                            self._storage.apagar(bucket, caminho)
                        except Exception:  # arquivo já removido: segue
                            logger.warning("arquivo não apagado", extra={"bucket": bucket})
                self._repo.excluir_titular(pedido["usuario_id"], pedido["email"])
                self._repo.concluir(pedido["id"])
                feitos += 1
            except Exception as exc:
                logger.exception("falha na exclusão de conta", extra={"pedido": str(pedido["id"])})
                self._repo.concluir(pedido["id"], erro=str(exc)[:500])
        return feitos
