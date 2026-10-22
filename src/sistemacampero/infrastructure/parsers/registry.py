"""Registro de adapters: (marca, tecnologia) -> adapter, com detecção pelo conteúdo."""

from __future__ import annotations

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.ports import TelemetryAdapter
from sistemacampero.domain.telemetry import ParseContext
from sistemacampero.infrastructure.parsers.john_deere_gen4 import JohnDeereGen4Adapter


def _chave(valor: str) -> str:
    return valor.strip().lower().replace(" ", "_").replace("-", "_")


class RegistroAdapters:
    def __init__(self, adapters: list[TelemetryAdapter] | None = None) -> None:
        self._por_chave: dict[tuple[str, str], TelemetryAdapter] = {}
        for a in adapters or []:
            self.registrar(a)

    def registrar(self, adapter: TelemetryAdapter) -> None:
        chave = (_chave(adapter.brand), _chave(adapter.technology))
        if chave in self._por_chave:
            raise ValueError(f"adapter duplicado para {chave}")
        self._por_chave[chave] = adapter

    def todos(self) -> list[TelemetryAdapter]:
        return list(self._por_chave.values())

    def escolher(self, head: bytes, ctx: ParseContext) -> TelemetryAdapter:
        if ctx.marca and ctx.tecnologia:
            adapter = self._por_chave.get((_chave(ctx.marca), _chave(ctx.tecnologia)))
            if adapter is None:
                raise Invalido(
                    f"Marca/tecnologia não suportada: {ctx.marca}/{ctx.tecnologia}.",
                    codigo="FORMATO_NAO_SUPORTADO",
                    suportados=[f"{m}/{t}" for m, t in self._por_chave],
                )
            if not adapter.can_parse(head, ctx.nome_arquivo):
                raise Invalido(
                    f"O arquivo não parece ser {ctx.marca}/{ctx.tecnologia}.",
                    codigo="FORMATO_NAO_CONFERE",
                )
            return adapter
        candidatos = [a for a in self._por_chave.values() if a.can_parse(head, ctx.nome_arquivo)]
        if len(candidatos) != 1:
            raise Invalido(
                "Não foi possível identificar o formato do arquivo; informe marca e tecnologia.",
                codigo="FORMATO_NAO_SUPORTADO",
                suportados=[f"{m}/{t}" for m, t in self._por_chave],
            )
        return candidatos[0]


def registro_padrao() -> RegistroAdapters:
    """Adapters disponíveis em produção. Nova marca: ver docs/como-adicionar-marca.md."""
    return RegistroAdapters([JohnDeereGen4Adapter()])
