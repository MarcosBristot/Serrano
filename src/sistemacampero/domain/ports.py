"""Portas (interfaces) que a infraestrutura implementa.

Portas que dependem de tipos da aplicação (ex.: gravar o resultado do processamento)
ficam na própria camada de aplicação.
"""

from __future__ import annotations

from typing import Any, BinaryIO, Protocol
from uuid import UUID

from sistemacampero.domain.ingestao import (
    ArquivoRegistrado,
    Job,
    NovoArquivo,
    StatusArquivo,
    TipoJob,
)
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


class Armazenamento(Protocol):
    """Storage de objetos (Supabase Storage em produção, disco local em dev/teste)."""

    def gravar(self, bucket: str, caminho: str, dados: BinaryIO, content_type: str) -> None:
        """Sobrescreve se existir (caminhos são por sha256: mesmo caminho = mesmo conteúdo)."""
        ...

    def ler(self, bucket: str, caminho: str) -> bytes: ...

    def copiar_para(self, bucket: str, caminho: str, destino: BinaryIO) -> None:
        """Download em streaming (zip grande não passa pela memória)."""
        ...

    def existe(self, bucket: str, caminho: str) -> bool: ...

    def apagar(self, bucket: str, caminho: str) -> None: ...

    def url_assinada(self, bucket: str, caminho: str, expira_s: int) -> str: ...

    def verificar(self) -> None:
        """Levanta se o Storage estiver inacessível (usado no /ready)."""
        ...


class RepositorioIngestao(Protocol):
    def registrar_arquivo(
        self, novo: NovoArquivo, enfileirar: TipoJob | None, chave_job: str | None = None
    ) -> ArquivoRegistrado:
        """Insere o arquivo e o job NA MESMA transação; dedupe por (org, sha256)."""
        ...

    def criar_lote(self, organizacao_id: UUID, usuario_id: UUID | None, origem: str) -> UUID: ...

    def obter_arquivo(self, organizacao_id: UUID, arquivo_id: UUID) -> dict[str, Any] | None: ...

    def marcar_arquivo(
        self, organizacao_id: UUID, arquivo_id: UUID, status: StatusArquivo, motivo: str | None
    ) -> None: ...


class FilaDeJobs(Protocol):
    def reivindicar(self, worker_id: str, lease_s: int) -> Job | None:
        """Pega o próximo job pendente (FOR UPDATE SKIP LOCKED) e o marca como executando."""
        ...

    def renovar(self, job_id: UUID, worker_id: str, lease_s: int) -> bool:
        """Heartbeat. False se o job não é mais deste worker (lease perdido)."""
        ...

    def cancelamento_solicitado(self, job_id: UUID) -> bool: ...

    def progresso(self, job_id: UUID, dados: dict[str, Any]) -> None: ...

    def concluir(self, job_id: UUID, worker_id: str, resultado: dict[str, Any]) -> None: ...

    def falhar(self, job_id: UUID, worker_id: str, erro: str, definitivo: bool = False) -> str:
        """Agenda retentativa com backoff ou manda para 'morto'. Devolve o novo status."""
        ...

    def marcar_cancelado(self, job_id: UUID, worker_id: str) -> None: ...

    def recolher_vencidos(self) -> int:
        """Reaper: devolve à fila os jobs cujo lease venceu (worker morreu)."""
        ...
