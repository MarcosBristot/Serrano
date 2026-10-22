"""Verificação do JWT do Supabase Auth.

- Chaves assimétricas (ES256/RS256): JWKS em ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``,
  em cache; um ``kid`` desconhecido força um refresh (rotação de chave), no máximo 1x/30 s.
- HS256 (segredo legado): só se ``SUPABASE_JWT_SECRET`` estiver definido.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import jwt

from sistemacampero.domain.errors import NaoAutenticado

_ALGS_ASSIMETRICOS = ("ES256", "RS256", "EdDSA")
_REFRESH_MINIMO_S = 30.0


def buscar_jwks_http(url: str) -> Callable[[], dict[str, Any]]:
    def buscar() -> dict[str, Any]:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        dados: dict[str, Any] = resp.json()
        return dados

    return buscar


class CacheJwks:
    def __init__(
        self,
        buscar: Callable[[], dict[str, Any]],
        ttl_s: float = 600,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._buscar = buscar
        self._ttl = ttl_s
        self._relogio = relogio
        self._chaves: dict[str, jwt.PyJWK] = {}
        self._carregado_em: float | None = None
        self._lock = threading.Lock()

    def _recarregar(self) -> None:
        jwks = jwt.PyJWKSet.from_dict(self._buscar())
        self._chaves = {k.key_id: k for k in jwks.keys if k.key_id}
        self._carregado_em = self._relogio()

    def chave(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            agora = self._relogio()
            idade = None if self._carregado_em is None else agora - self._carregado_em
            vencido = idade is None or idade > self._ttl
            # kid desconhecido = provável rotação de chave: recarrega, com limite de frequência.
            kid_novo = kid not in self._chaves and idade is not None and idade > _REFRESH_MINIMO_S
            if vencido or kid_novo:
                self._recarregar()
            try:
                return self._chaves[kid]
            except KeyError:
                raise NaoAutenticado("Chave de assinatura desconhecida.") from None


class VerificadorJwtSupabase:
    def __init__(
        self,
        *,
        audience: str,
        issuer: str | None,
        jwks: CacheJwks | None,
        segredo_hs256: str | None,
    ) -> None:
        if jwks is None and not segredo_hs256:
            raise ValueError("Informe JWKS ou segredo HS256.")
        self._audience = audience
        self._issuer = issuer
        self._jwks = jwks
        self._segredo = segredo_hs256

    def verificar(self, token: str) -> tuple[UUID, str | None]:
        try:
            cabecalho = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise NaoAutenticado("Token malformado.") from None

        alg = cabecalho.get("alg")
        chave: Any
        if alg == "HS256" and self._segredo:
            chave, algs = self._segredo, ["HS256"]
        elif alg in _ALGS_ASSIMETRICOS and self._jwks is not None:
            kid = cabecalho.get("kid")
            if not kid:
                raise NaoAutenticado("Token sem 'kid'.")
            chave, algs = self._jwks.chave(kid), [alg]
        else:
            raise NaoAutenticado("Algoritmo de assinatura não aceito.")

        try:
            claims = jwt.decode(
                token,
                chave,
                algorithms=algs,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud"]},
                leeway=10,
            )
        except jwt.ExpiredSignatureError:
            raise NaoAutenticado("Token expirado.", codigo="TOKEN_EXPIRADO") from None
        except jwt.PyJWTError:
            raise NaoAutenticado("Token inválido.") from None

        if claims.get("role") != "authenticated":
            raise NaoAutenticado("Token não é de usuário autenticado.")
        try:
            usuario_id = UUID(str(claims["sub"]))
        except ValueError:
            raise NaoAutenticado("Token com 'sub' inválido.") from None
        email = claims.get("email")
        return usuario_id, email if isinstance(email, str) and email else None
