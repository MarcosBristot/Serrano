"""Adapters por fabricante e registro dos adapters disponíveis."""

from sistemacampero.domain.ports import ManufacturerAdapter
from sistemacampero.infrastructure.parsers.john_deere_gen4 import JohnDeereGen4Adapter


def default_adapters() -> list[ManufacturerAdapter]:
    """Adapters habilitados (novos fabricantes entram aqui)."""
    return [JohnDeereGen4Adapter()]
