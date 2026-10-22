from __future__ import annotations

import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from sistemacampero.domain.errors import NaoAutenticado
from sistemacampero.infrastructure.security.jwt import CacheJwks, VerificadorJwtSupabase
from tests.conftest import ISSUER, SEGREDO, emitir_token


def _hs256() -> VerificadorJwtSupabase:
    return VerificadorJwtSupabase(
        audience="authenticated", issuer=ISSUER, jwks=None, segredo_hs256=SEGREDO
    )


def test_hs256_valido() -> None:
    uid = uuid.uuid4()
    assert _hs256().verificar(emitir_token(uid)) == (uid, "gestor@example.com")


@pytest.mark.parametrize(
    ("kwargs", "codigo"),
    [
        ({"exp_em_s": -60}, "TOKEN_EXPIRADO"),
        ({"aud": "outra"}, "NAO_AUTENTICADO"),
        ({"iss": "https://outro.supabase.co/auth/v1"}, "NAO_AUTENTICADO"),
        ({"role": "anon"}, "NAO_AUTENTICADO"),
        ({"segredo": "outro-segredo-com-pelo-menos-32-bytes!!"}, "NAO_AUTENTICADO"),
    ],
)
def test_hs256_rejeita(kwargs: dict[str, object], codigo: str) -> None:
    with pytest.raises(NaoAutenticado) as exc:
        _hs256().verificar(emitir_token(uuid.uuid4(), **kwargs))  # type: ignore[arg-type]
    assert exc.value.codigo == codigo


def test_rejeita_alg_none_e_lixo() -> None:
    sem_assinatura = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "role": "authenticated",
            "exp": int(time.time()) + 60,
        },
        key=None,
        algorithm="none",
    )
    for token in (sem_assinatura, "nao.e.jwt", ""):
        with pytest.raises(NaoAutenticado):
            _hs256().verificar(token)


def test_sub_que_nao_e_uuid() -> None:
    with pytest.raises(NaoAutenticado):
        _hs256().verificar(emitir_token("service-account"))


def _jwk_publico(chave: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, object]:
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(chave.public_key()))
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return jwk  # type: ignore[no-any-return]


def _es256(chave: ec.EllipticCurvePrivateKey, kid: str, sub: uuid.UUID) -> str:
    agora = int(time.time())
    return jwt.encode(
        {
            "sub": str(sub),
            "aud": "authenticated",
            "iss": ISSUER,
            "role": "authenticated",
            "iat": agora,
            "exp": agora + 300,
        },
        chave,
        algorithm="ES256",
        headers={"kid": kid},
    )


def test_jwks_es256_com_rotacao_de_chave() -> None:
    antiga, nova = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    publicadas = {"keys": [_jwk_publico(antiga, "k1")]}
    buscas = []
    agora = [1000.0]

    def buscar() -> dict[str, object]:
        buscas.append(agora[0])
        return publicadas

    cache = CacheJwks(buscar, ttl_s=600, relogio=lambda: agora[0])
    verif = VerificadorJwtSupabase(
        audience="authenticated", issuer=ISSUER, jwks=cache, segredo_hs256=None
    )
    uid = uuid.uuid4()
    assert verif.verificar(_es256(antiga, "k1", uid))[0] == uid
    assert len(buscas) == 1

    # Supabase rotaciona: kid novo aparece no JWKS; refresh forçado (após 30 s).
    publicadas = {"keys": [_jwk_publico(antiga, "k1"), _jwk_publico(nova, "k2")]}
    agora[0] += 31
    assert verif.verificar(_es256(nova, "k2", uid))[0] == uid
    assert len(buscas) == 2

    # kid desconhecido logo em seguida não martela o endpoint.
    with pytest.raises(NaoAutenticado):
        verif.verificar(_es256(nova, "k3", uid))
    assert len(buscas) == 2


def test_hs256_recusado_quando_so_ha_jwks() -> None:
    cache = CacheJwks(lambda: {"keys": []})
    verif = VerificadorJwtSupabase(
        audience="authenticated", issuer=ISSUER, jwks=cache, segredo_hs256=None
    )
    with pytest.raises(NaoAutenticado):
        verif.verificar(emitir_token(uuid.uuid4()))
