"""Regras de dependência entre camadas (DDD), verificadas pela AST dos módulos."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACOTE = Path(__file__).resolve().parents[2] / "src" / "sistemacampero"

PROIBIDOS = {
    "domain": {
        "fastapi",
        "starlette",
        "psycopg",
        "psycopg_pool",
        "httpx",
        "jwt",
        "uvicorn",
        "pydantic_settings",
        "sistemacampero.application",
        "sistemacampero.infrastructure",
        "sistemacampero.interfaces",
    },
    "application": {
        "fastapi",
        "starlette",
        "psycopg",
        "psycopg_pool",
        "httpx",
        "jwt",
        "uvicorn",
        "pydantic_settings",
        "sistemacampero.infrastructure",
        "sistemacampero.interfaces",
    },
    "infrastructure": {"fastapi", "starlette", "sistemacampero.interfaces"},
}


def _imports(arquivo: Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


def _usa_environ(arquivo: Path) -> bool:
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Attribute) and no.attr in {"environ", "getenv"}:
            return True
    return False


@pytest.mark.parametrize("camada", sorted(PROIBIDOS))
def test_camada_respeita_dependencias(camada: str) -> None:
    violacoes = []
    for arq in (PACOTE / camada).rglob("*.py"):
        for nome in _imports(arq):
            if any(nome == p or nome.startswith(p + ".") for p in PROIBIDOS[camada]):
                violacoes.append(f"{arq.relative_to(PACOTE)} importa {nome}")
    assert not violacoes, "\n".join(violacoes)


@pytest.mark.parametrize("camada", ["domain", "application", "infrastructure"])
def test_sem_os_environ_fora_da_borda(camada: str) -> None:
    usos = [str(a.relative_to(PACOTE)) for a in (PACOTE / camada).rglob("*.py") if _usa_environ(a)]
    assert not usos, f"leia configuração só via Settings: {usos}"
