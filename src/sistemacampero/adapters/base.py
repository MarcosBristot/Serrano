"""Contrato dos adapters por fabricante."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sistemacampero.schema.universal import ParsedSession


class ManufacturerAdapter(Protocol):
    name: str
    version: str

    def can_parse(self, path: Path) -> bool:
        """Reconhece (barato, sem ler o arquivo todo) se o arquivo é deste fabricante."""

    def parse(self, path: Path) -> ParsedSession:
        """Converte um arquivo bruto em ``ParsedSession`` (schema universal)."""
