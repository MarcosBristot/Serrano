"""Cópia local dos usuários do Supabase Auth (hospedagem em casa)."""

from __future__ import annotations

from uuid import UUID

from sistemacampero.infrastructure.persistence.db import Database


class EspelhoDeUsuarios:
    """Login no Supabase Auth, dados no Postgres local: o usuário do JWT precisa existir em
    ``auth.users`` (membros, autoria de alertas etc. apontam para lá). No Supabase, não é usado."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._vistos: set[UUID] = set()

    def garantir(self, usuario_id: UUID, email: str | None) -> None:
        if usuario_id in self._vistos:
            return
        with self._db.transacao(None) as conn:
            conn.execute("select auth.espelhar_usuario(%s, %s)", (usuario_id, email))
        self._vistos.add(usuario_id)
