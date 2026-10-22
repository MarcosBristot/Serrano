"""Casos de uso de ingestão: receber arquivo (API/CLI) e executar os jobs (worker).

Etapa 1 (bruto): o arquivo vai para ``brutos/<org>/<sha256>.<ext>`` (imutável) e, na
mesma transação, nascem a linha em ``arquivos_brutos`` e o job. Não existe "arquivo sem
job" nem "job sem arquivo". O processamento (etapas 2 a 5) roda no worker.
"""

from __future__ import annotations

import hashlib
import io
import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol, cast
from uuid import UUID

from sistemacampero.application.cadastro import ServicoCadastro
from sistemacampero.application.processamento import ProcessadorDeArquivo, ResultadoSessao
from sistemacampero.domain.cadastro import ImportacaoCadastro
from sistemacampero.domain.errors import GrandeDemais, Invalido
from sistemacampero.domain.ingestao import (
    BUCKET_BRUTOS,
    BUCKET_LIMPOS,
    ArquivoRegistrado,
    Job,
    NovoArquivo,
    StatusArquivo,
    TipoArquivo,
    TipoJob,
    caminho_bruto,
    caminho_limpo,
    nome_para_exibicao,
    tipo_do_arquivo,
)
from sistemacampero.domain.ports import Armazenamento, RepositorioCadastro, RepositorioIngestao
from sistemacampero.domain.services import zip_seguro
from sistemacampero.domain.services.geo import LocalizadorDeTalhoes
from sistemacampero.domain.telemetry import EmptyFile, ParseContext

logger = logging.getLogger(__name__)

_CONTENT_TYPE = {
    TipoArquivo.JDL: "application/octet-stream",
    TipoArquivo.ZIP: "application/zip",
    TipoArquivo.MASTERDATA: "application/xml",
    TipoArquivo.GJSON: "application/geo+json",
}
_ASSINATURA = {TipoArquivo.JDL: b"\x0d", TipoArquivo.ZIP: b"PK\x03\x04"}


class RepositorioResultados(Protocol):
    def gravar_sessao(
        self,
        organizacao_id: UUID,
        arquivo_id: UUID,
        r: ResultadoSessao,
        caminho_limpo: str | None,
        versao_regras: str,
        config_regras: dict[str, Any],
    ) -> tuple[StatusArquivo, str | None]:
        """Sessão, telemetria, métricas e alertas numa transação (idempotente)."""
        ...


class ControleJob(Protocol):
    def verificar(self) -> None:
        """Levanta ``Cancelado`` se pediram cancelamento (ou o lease foi perdido)."""
        ...

    def progresso(self, dados: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class ResultadoUpload:
    arquivo_id: UUID
    job_id: UUID | None
    duplicado: bool
    status: StatusArquivo
    sha256: str
    tipo: TipoArquivo


def _hash_e_tamanho(conteudo: BinaryIO, max_bytes: int) -> tuple[str, int, bytes]:
    h, total, cabeca = hashlib.sha256(), 0, b""
    while parte := conteudo.read(1024 * 1024):
        if not cabeca:
            cabeca = parte[:64]
        total += len(parte)
        if total > max_bytes:
            raise GrandeDemais(
                f"Arquivo maior que o limite de {max_bytes // 1024**2} MB.",
                limite_mb=max_bytes // 1024**2,
            )
        h.update(parte)
    conteudo.seek(0)
    return h.hexdigest(), total, cabeca


class ServicoIngestao:
    def __init__(self, repo: RepositorioIngestao, storage: Armazenamento, max_bytes: int) -> None:
        self._repo = repo
        self._storage = storage
        self._max_bytes = max_bytes

    def receber(
        self,
        organizacao_id: UUID,
        nome: str,
        conteudo: BinaryIO,
        *,
        marca: str | None = None,
        tecnologia: str | None = None,
        lote_id: UUID | None = None,
    ) -> ResultadoUpload:
        """Um arquivo por chamada (.jdl ou .zip). Reenvio do mesmo conteúdo = duplicado."""
        tipo = tipo_do_arquivo(nome)
        if tipo not in (TipoArquivo.JDL, TipoArquivo.ZIP):
            raise Invalido(
                "Envie um arquivo .jdl ou .zip da pasta do monitor.",
                codigo="FORMATO_NAO_SUPORTADO",
            )
        sha, tamanho, cabeca = _hash_e_tamanho(conteudo, self._max_bytes)
        if tamanho == 0 or not cabeca.startswith(_ASSINATURA[tipo]):
            raise Invalido(
                f"O conteúdo não parece um arquivo .{tipo.value} válido.",
                codigo="FORMATO_NAO_CONFERE",
            )
        caminho = caminho_bruto(organizacao_id, sha, tipo)
        if not self._storage.existe(BUCKET_BRUTOS, caminho):
            self._storage.gravar(BUCKET_BRUTOS, caminho, conteudo, _CONTENT_TYPE[tipo])
        reg = self._repo.registrar_arquivo(
            NovoArquivo(
                organizacao_id=organizacao_id,
                sha256=sha,
                nome_original=nome_para_exibicao(nome),
                tipo=tipo,
                tamanho_bytes=tamanho,
                caminho_storage=caminho,
                marca=marca,
                tecnologia=tecnologia,
                lote_id=lote_id,
            ),
            TipoJob.EXPANDIR_ZIP if tipo is TipoArquivo.ZIP else TipoJob.PROCESSAR_ARQUIVO,
        )
        return ResultadoUpload(reg.arquivo_id, reg.job_id, reg.duplicado, reg.status, sha, tipo)


LeitorCadastro = Callable[[bytes, dict[str, bytes]], ImportacaoCadastro]


class ExecutorDeJobs:
    """Handlers idempotentes: reexecutar um job não duplica nada."""

    def __init__(
        self,
        repo: RepositorioIngestao,
        storage: Armazenamento,
        processador: ProcessadorDeArquivo,
        resultados: RepositorioResultados,
        versao_regras: str,
        config_regras: dict[str, Any],
        cadastro: RepositorioCadastro,
        leitor_cadastro: LeitorCadastro,
        limites_zip: zip_seguro.LimitesZip | None = None,
    ) -> None:
        self._repo = repo
        self._cadastro = cadastro
        self._leitor_cadastro = leitor_cadastro
        self._servico_cadastro = ServicoCadastro(cadastro, repo)
        self._storage = storage
        self._processador = processador
        self._resultados = resultados
        self._versao = versao_regras
        self._config = config_regras
        self._limites_zip = limites_zip or zip_seguro.LimitesZip()
        self._handlers: dict[TipoJob, Callable[[Job, ControleJob], dict[str, Any]]] = {
            TipoJob.PROCESSAR_ARQUIVO: self._processar_arquivo,
            TipoJob.EXPANDIR_ZIP: self._expandir_zip,
            TipoJob.IMPORTAR_GEN4: self._importar_gen4,
        }

    def executar(self, job: Job, controle: ControleJob) -> dict[str, Any]:
        return self._handlers[job.tipo](job, controle)

    def ao_desistir(self, job: Job, erro: str) -> None:
        """Job morto (tentativas esgotadas): o arquivo fica em 'erro' com o motivo."""
        arquivo = job.payload.get("arquivo_id")
        if arquivo:
            self._repo.marcar_arquivo(
                job.organizacao_id, UUID(arquivo), StatusArquivo.ERRO, erro[:500]
            )

    # ------------------------------------------------------------ processar
    def _processar_arquivo(self, job: Job, controle: ControleJob) -> dict[str, Any]:
        org, arquivo_id = job.organizacao_id, UUID(job.payload["arquivo_id"])
        arquivo = self._repo.obter_arquivo(org, arquivo_id)
        if arquivo is None:
            return {"status": "arquivo_inexistente"}
        self._repo.marcar_arquivo(org, arquivo_id, StatusArquivo.PROCESSANDO, None)
        dados = self._storage.ler(BUCKET_BRUTOS, str(arquivo["caminho_storage"]))
        controle.verificar()

        ctx = ParseContext(
            nome_arquivo=str(arquivo["nome_original"]),
            marca=arquivo.get("marca"),
            tecnologia=arquivo.get("tecnologia"),
        )
        # Talhões da organização uma vez por job; o manual (correção do gestor) manda.
        talhoes = LocalizadorDeTalhoes(self._cadastro.contornos(org))
        manual = self._cadastro.talhao_manual(org, arquivo_id)
        try:
            r = self._processador.processar(dados, ctx, talhoes=talhoes, talhao_manual_id=manual)
        except Invalido as exc:  # formato errado/corrompido: não adianta tentar de novo
            self._repo.marcar_arquivo(
                org, arquivo_id, StatusArquivo.REJEITADO, f"{exc.codigo}: {exc.mensagem}"
            )
            return {"status": StatusArquivo.REJEITADO.value, "motivo": exc.codigo}
        if isinstance(r, EmptyFile):
            self._repo.marcar_arquivo(
                org, arquivo_id, StatusArquivo.VAZIO, f"{r.motivo}: {r.explicacao}"
            )
            return {"status": StatusArquivo.VAZIO.value, "motivo": r.motivo}
        controle.progresso({"etapa": "gravando", "amostras": len(r.limpo)})
        controle.verificar()

        limpo = caminho_limpo(org, r.sessao.sha256)
        buf = io.BytesIO()
        r.limpo.to_parquet(buf, index=False)
        buf.seek(0)
        self._storage.gravar(BUCKET_LIMPOS, limpo, buf, "application/vnd.apache.parquet")
        controle.verificar()

        status, motivo = self._resultados.gravar_sessao(
            org, arquivo_id, r, limpo, self._versao, self._config
        )
        return {
            "status": status.value,
            "motivo": motivo,
            "qualidade": r.qualidade.score,
            "alertas": len(r.alertas),
        }

    # ------------------------------------------------------------ zip
    def _expandir_zip(self, job: Job, controle: ControleJob) -> dict[str, Any]:
        org, zip_id = job.organizacao_id, UUID(job.payload["arquivo_id"])
        arquivo = self._repo.obter_arquivo(org, zip_id)
        if arquivo is None:
            return {"status": "arquivo_inexistente"}
        self._repo.marcar_arquivo(org, zip_id, StatusArquivo.PROCESSANDO, None)
        lote_id = arquivo.get("lote_id") or job.lote_id
        contagem = {"jdl": 0, "masterdata": 0, "gjson": 0, "duplicados": 0}
        masterdata: list[UUID] = []
        # nome no zip -> arquivo (novo ou já existente): o .gjson repetido de outro pendrive
        # tem como "pai" o primeiro zip, então a relação vai explícita no payload.
        gjson: dict[str, str] = {}
        with tempfile.TemporaryFile() as arquivo_tmp:
            tmp = cast(BinaryIO, arquivo_tmp)
            self._storage.copiar_para(BUCKET_BRUTOS, str(arquivo["caminho_storage"]), tmp)
            tmp.seek(0)
            try:
                for i, entrada in enumerate(zip_seguro.expandir(tmp, self._limites_zip)):
                    if i % 50 == 0:
                        controle.verificar()
                        controle.progresso({"entradas_lidas": i, **contagem})
                    reg = self._registrar_entrada(org, zip_id, lote_id, arquivo, entrada)
                    if entrada.tipo is TipoArquivo.MASTERDATA:
                        masterdata.append(reg.arquivo_id)
                    elif entrada.tipo is TipoArquivo.GJSON:
                        gjson[entrada.nome] = str(reg.arquivo_id)
                    contagem[entrada.tipo.value] += 1
                    contagem["duplicados"] += int(reg.duplicado)
            except Invalido as exc:
                self._repo.marcar_arquivo(
                    org, zip_id, StatusArquivo.REJEITADO, f"{exc.codigo}: {exc.mensagem}"
                )
                return {"status": StatusArquivo.REJEITADO.value, "motivo": exc.codigo, **contagem}
        # Cadastro do monitor antes dos .jdl (prioridade menor = antes na fila).
        for md_id in masterdata:  # um por zip (chave = zip): pendrive novo reimporta
            self._repo.enfileirar(
                org,
                TipoJob.IMPORTAR_GEN4,
                {"arquivo_id": str(md_id), "gjson": gjson},
                lote_id,
                f"importar_gen4:{zip_id}:{md_id}",
            )
        self._repo.marcar_arquivo(org, zip_id, StatusArquivo.PROCESSADO, None)
        return {"status": StatusArquivo.PROCESSADO.value, **contagem}

    # ------------------------------------------------------------ cadastro Gen4
    def _importar_gen4(self, job: Job, controle: ControleJob) -> dict[str, Any]:
        org, md_id = job.organizacao_id, UUID(job.payload["arquivo_id"])
        md = self._repo.obter_arquivo(org, md_id)
        if md is None:
            return {"status": "arquivo_inexistente"}
        xml = self._storage.ler(BUCKET_BRUTOS, str(md["caminho_storage"]))
        gjsons: list[tuple[str, dict[str, Any]]] = []
        for nome, ident in job.payload.get("gjson", {}).items():
            g = self._repo.obter_arquivo(org, UUID(ident))
            if g is not None:
                gjsons.append((nome, g))
        por_nome = {
            nome: self._storage.ler(BUCKET_BRUTOS, str(g["caminho_storage"])) for nome, g in gjsons
        }
        controle.verificar()
        try:
            cadastro = self._leitor_cadastro(xml, por_nome)
        except Invalido as exc:
            self._repo.marcar_arquivo(
                org, md_id, StatusArquivo.REJEITADO, f"{exc.codigo}: {exc.mensagem}"
            )
            return {"status": StatusArquivo.REJEITADO.value, "motivo": exc.codigo}
        resumo = self._cadastro.importar(org, cadastro)
        relocalizadas = 0
        if resumo.contornos_novos:
            # Sessões já gravadas sem esses contornos; as pendentes já vão localizar.
            relocalizadas = self._servico_cadastro.relocalizar(
                org, self._cadastro.arquivos_para_relocalizar(org)
            )
        self._repo.marcar_arquivo(
            org, md_id, StatusArquivo.PROCESSADO, "; ".join(cadastro.avisos)[:500] or None
        )
        for _, g in gjsons:
            self._repo.marcar_arquivo(org, g["id"], StatusArquivo.PROCESSADO, None)
        return {
            "status": StatusArquivo.PROCESSADO.value,
            "fazendas": resumo.fazendas,
            "talhoes": resumo.talhoes,
            "contornos_novos": resumo.contornos_novos,
            "contornos_preservados": resumo.contornos_preservados,
            "implementos": resumo.implementos,
            "operadores": resumo.operadores,
            "sessoes_relocalizadas": relocalizadas,
        }

    def _registrar_entrada(
        self,
        org: UUID,
        zip_id: UUID,
        lote_id: UUID | None,
        arquivo_zip: dict[str, Any],
        entrada: zip_seguro.EntradaZip,
    ) -> ArquivoRegistrado:
        sha = hashlib.sha256(entrada.conteudo).hexdigest()
        caminho = caminho_bruto(org, sha, entrada.tipo)
        if not self._storage.existe(BUCKET_BRUTOS, caminho):
            self._storage.gravar(
                BUCKET_BRUTOS, caminho, io.BytesIO(entrada.conteudo), _CONTENT_TYPE[entrada.tipo]
            )
        # MasterData/SpatialFiles ficam guardados para o importador Gen4 (M4).
        job = TipoJob.PROCESSAR_ARQUIVO if entrada.tipo is TipoArquivo.JDL else None
        return self._repo.registrar_arquivo(
            NovoArquivo(
                organizacao_id=org,
                sha256=sha,
                nome_original=entrada.nome,
                tipo=entrada.tipo,
                tamanho_bytes=len(entrada.conteudo),
                caminho_storage=caminho,
                marca=arquivo_zip.get("marca"),
                tecnologia=arquivo_zip.get("tecnologia"),
                lote_id=lote_id,
                arquivo_pai_id=zip_id,
            ),
            job,
        )
