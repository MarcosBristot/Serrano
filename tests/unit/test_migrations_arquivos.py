"""Checagens estáticas das migrations (rodam sem banco)."""

from __future__ import annotations

import re

from sistemacampero.infrastructure.persistence.migrations import MIGRATIONS_DIR, listar_migrations


def test_nomes_unicos_e_ordenados() -> None:
    itens = listar_migrations()
    versoes = [v for v, _, _ in itens]
    assert versoes == sorted(versoes)
    assert len(versoes) == len(set(versoes))


def test_toda_tabela_publica_tem_rls() -> None:
    sql = "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS_DIR.glob("*.sql")))
    criadas = set(re.findall(r"create table public\.(\w+) \(", sql))
    com_rls = set(re.findall(r"alter table public\.(\w+) enable row level security", sql))
    geradas = re.search(r"leitura_frontend text\[\] := array\[(.*?)\];", sql, re.S)
    extras = re.search(r"array\['convites'.*?\]", sql)
    assert geradas and extras
    com_rls |= set(re.findall(r"'(\w+)'", geradas.group(1) + extras.group(0)))
    assert criadas - com_rls == set()


def test_sem_segredos_nas_migrations() -> None:
    for arq in MIGRATIONS_DIR.glob("*.sql"):
        texto = arq.read_text(encoding="utf-8")
        assert not re.search(r"password\s+'[^<]", texto, re.I), arq.name
        assert "eyJ" not in texto, arq.name  # JWT
