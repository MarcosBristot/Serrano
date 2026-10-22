"""Portas (interfaces) que a infraestrutura implementa.

As portas de telemetria, Storage, fila e notificação entram nos marcos M2, M3 e M6.
"""

from __future__ import annotations

from typing import BinaryIO, Protocol
from uuid import UUID

from sistemacampero.domain.telemetry import EmptyFile, ParseContext, ParsedSession
from sistemacampero.domain.tenancy import Organizacao, Vinculo


class TelemetryAdapter(Protocol):
    """Lê o arquivo de um fabricante/tecnologia e devolve o schema universal.

    Contrato completo em ``docs/como-adicionar-marca.md`` e ``tests/contrato``.
    """

    brand: str
    technology: str
    version: str

    def can_parse(self, head: bytes, filename: str) -> bool:
        """Decide pelos primeiros bytes e pelo nome (sem ler o arquivo inteiro)."""
        ...

    def parse(self, data: BinaryIO, ctx: ParseContext) -> ParsedSession | EmptyFile:
        """Levanta ``ArquivoInvalido`` se o formato estiver corrompido."""
        ...


class RegistroDeAdapters(Protocol):
    def escolher(self, head: bytes, ctx: ParseContext) -> TelemetryAdapter:
        """Adapter da marca/tecnologia do contexto ou, sem elas, por detecção.

        Levanta ``Invalido`` (``FORMATO_NAO_SUPORTADO``) se nenhum servir.
        """
        ...


class RepositorioOrganizacoes(Protocol):
    def vinculos_do_usuario(self, usuario_id: UUID) -> list[Vinculo]:
        """Organizações de que o usuário participa (ignora a organização ativa)."""
        ...

    def criar_organizacao(
        self, org: Organizacao, dono_id: UUID, plano_codigo: str, dias_trial: int
    ) -> None:
        """Cria organização, membro dono e assinatura em uma transação.

        Levanta ``Conflito`` (código ``SLUG_EM_USO``) se o slug já existir.
        """
        ...


class VerificadorDeToken(Protocol):
    def verificar(self, token: str) -> tuple[UUID, str | None]:
        """Valida o JWT e devolve (usuario_id, email). Levanta ``NaoAutenticado``."""
        ...


class VerificadorDeProntidao(Protocol):
    def verificar(self) -> dict[str, str]:
        """Checa dependências externas; devolve {nome: 'ok' | mensagem de erro}."""
        ...
