"""Envio de notificações: e-mail (SMTP genérico) e webhook (assinado com HMAC).

WhatsApp fica só como tipo aceito no cadastro (porta), sem envio, até haver provedor.
O segredo do webhook é guardado cifrado (Fernet, ``CHAVE_CIFRAGEM``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from sistemacampero.domain.errors import Invalido


class Cifra:
    def __init__(self, chave: str | None) -> None:
        self._f = Fernet(chave.encode()) if chave else None

    def cifrar(self, texto: str) -> str:
        if self._f is None:
            raise Invalido(
                "Servidor sem CHAVE_CIFRAGEM: não é possível guardar segredo de webhook.",
                codigo="SEM_CHAVE_CIFRAGEM",
            )
        return self._f.encrypt(texto.encode()).decode()

    def decifrar(self, texto: str | None) -> str | None:
        if texto is None or self._f is None:
            return None
        try:
            return self._f.decrypt(texto.encode()).decode()
        except InvalidToken:
            return None


def assinatura_webhook(segredo: str, corpo: bytes, timestamp: int) -> str:
    """``X-Campero-Assinatura: t=<ts>,v1=<hmac_sha256(t.corpo)>`` (estilo Stripe)."""
    mac = hmac.new(segredo.encode(), f"{timestamp}.".encode() + corpo, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


class Notificador:
    def __init__(
        self,
        cifra: Cifra,
        smtp: dict[str, Any] | None,
        frontend_url: str | None,
        http: httpx.Client | None = None,
    ) -> None:
        self._cifra = cifra
        self._smtp = smtp
        self._frontend = (frontend_url or "").rstrip("/")
        self._http = http or httpx.Client(timeout=10.0)

    def _conteudo(self, alerta: dict[str, Any]) -> dict[str, Any]:
        return {
            "evento": "alerta.criado",
            "alerta": {
                "id": str(alerta["id"]),
                "tipo": alerta["tipo"],
                "severidade": alerta["severidade"],
                "mensagem": alerta["mensagem"],
                "maquina": alerta.get("apelido") or alerta.get("serial"),
                "talhao": alerta.get("talhao_nome"),
                "inicio": alerta["inicio"].isoformat() if alerta.get("inicio") else None,
                "url": f"{self._frontend}/alertas/{alerta['id']}" if self._frontend else None,
            },
        }

    def enviar(self, alerta: dict[str, Any], destino: dict[str, Any]) -> None:
        """Levanta em falha (a outbox agenda nova tentativa)."""
        conteudo = self._conteudo(alerta)
        if destino["tipo"] == "webhook":
            corpo = json.dumps(conteudo, ensure_ascii=False).encode()
            cabecalhos = {"Content-Type": "application/json"}
            segredo = self._cifra.decifrar(destino.get("segredo_cifrado"))
            if segredo:
                cabecalhos["X-Campero-Assinatura"] = assinatura_webhook(
                    segredo, corpo, int(time.time())
                )
            resp = self._http.post(destino["destino"], content=corpo, headers=cabecalhos)
            if resp.status_code >= 300:
                raise RuntimeError(f"webhook respondeu HTTP {resp.status_code}")
        elif destino["tipo"] == "email":
            self._email(destino["destino"], conteudo["alerta"])
        else:
            raise RuntimeError(f"tipo de destino sem envio implementado: {destino['tipo']}")

    def convite(self, para: str, papel: str, token: str) -> None:
        if not self._smtp or not self._frontend:
            raise RuntimeError("SMTP ou FRONTEND_URL não configurados")
        msg = EmailMessage()
        msg["Subject"] = "[Campero] Você foi convidado para uma organização"
        msg["From"] = self._smtp["remetente"]
        msg["To"] = para
        msg.set_content(
            f"Você foi convidado como {papel} no Sistema Campero.\n\n"
            f"Aceite em: {self._frontend}/convite?token={token}\n\n"
            "O convite vale por 7 dias."
        )
        self._enviar_email(msg)

    def _enviar_email(self, msg: EmailMessage) -> None:
        assert self._smtp is not None
        with smtplib.SMTP(self._smtp["host"], self._smtp["porta"], timeout=15) as s:
            if self._smtp.get("tls", True):
                s.starttls(context=ssl.create_default_context())
            if self._smtp.get("usuario"):
                s.login(self._smtp["usuario"], self._smtp["senha"])
            s.send_message(msg)

    def _email(self, para: str, a: dict[str, Any]) -> None:
        if not self._smtp:
            raise RuntimeError("SMTP não configurado")
        msg = EmailMessage()
        msg["Subject"] = f"[Campero] {a['severidade'].upper()}: {a['tipo'].replace('_', ' ')}"
        msg["From"] = self._smtp["remetente"]
        msg["To"] = para
        linhas = [a["mensagem"], ""]
        if a.get("maquina"):
            linhas.append(f"Máquina: {a['maquina']}")
        if a.get("talhao"):
            linhas.append(f"Talhão: {a['talhao']}")
        if a.get("url"):
            linhas += ["", a["url"]]
        msg.set_content("\n".join(linhas))
        self._enviar_email(msg)
