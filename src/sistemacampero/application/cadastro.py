"""Casos de uso de cadastro que mexem na localização das sessões.

Mudar um contorno ou corrigir o talhão de uma sessão reprocessa as sessões afetadas
(a partir do bruto, idempotente). Assim talhão, área por cobertura e L/ha ficam
coerentes com o cadastro atual.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sistemacampero.domain.cadastro import OrigemContorno
from sistemacampero.domain.ingestao import TipoJob
from sistemacampero.domain.ports import RepositorioCadastro, RepositorioIngestao
from sistemacampero.domain.services.geo import normalizar_contorno


class ServicoCadastro:
    def __init__(self, repo: RepositorioCadastro, ingestao: RepositorioIngestao) -> None:
        self._repo = repo
        self._ingestao = ingestao

    def relocalizar(self, org: UUID, arquivos: list[UUID]) -> int:
        marca = uuid.uuid4().hex[:12]
        for arquivo in dict.fromkeys(arquivos):
            self._ingestao.enfileirar(
                org,
                TipoJob.PROCESSAR_ARQUIVO,
                {"arquivo_id": str(arquivo), "motivo": "relocalizar"},
                chave=f"relocalizar:{marca}:{arquivo}",
            )
        return len(dict.fromkeys(arquivos))

    def definir_contorno(
        self,
        org: UUID,
        talhao_id: UUID,
        geojson: dict[str, Any] | None,
        origem: OrigemContorno = OrigemContorno.UPLOAD,
    ) -> dict[str, Any]:
        """``geojson=None`` remove o contorno. Devolve o talhão e quantas sessões serão refeitas."""
        geom = normalizar_contorno(geojson) if geojson is not None else None
        # Sessões que estavam no talhão (contorno antigo) + as que tocam o novo.
        afetadas = self._repo.arquivos_para_relocalizar(org, geom, talhao_id) if geom else []
        talhao = self._repo.definir_contorno(org, talhao_id, geom, origem if geom else None)
        if geom is None:
            afetadas = self._repo.arquivos_para_relocalizar(org)
        return {**talhao, "sessoes_relocalizadas": self.relocalizar(org, afetadas)}

    def corrigir_sessao(self, org: UUID, sessao_id: UUID, campos: dict[str, Any]) -> int:
        """Talhão manual (ou ``None`` para voltar ao automático) e operador."""
        arquivo = self._repo.corrigir_sessao(org, sessao_id, campos)
        return self.relocalizar(org, [arquivo]) if "talhao_id" in campos else 0

    def ativar_maquina(self, org: UUID, maquina_id: UUID, ativa: bool) -> dict[str, Any]:
        maquina = self._repo.ativar_maquina(org, maquina_id, ativa)
        reabertos = 0 if ativa else self._ingestao.reabrir_bloqueados(org)
        return {**maquina, "arquivos_reabertos": reabertos}
