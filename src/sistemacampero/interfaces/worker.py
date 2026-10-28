"""Worker da fila Postgres: ``python -m sistemacampero.interfaces.worker``.

Um job por vez por processo (escala com réplicas). Heartbeat renova o lease enquanto o
handler roda; o reaper devolve à fila jobs de workers que morreram; SIGTERM termina o
job atual e sai (deploy sem perder trabalho).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from sistemacampero.application.ingestao import ExecutorDeJobs
from sistemacampero.domain.ingestao import Cancelado, Job
from sistemacampero.domain.ports import FilaDeJobs
from sistemacampero.infrastructure.logging_config import job_id_var

logger = logging.getLogger("sistemacampero.worker")


class LeasePerdido(Cancelado):
    """Outro worker assumiu o job (lease vencido): este para sem gravar o fim."""


class _Controle:
    def __init__(self, fila: FilaDeJobs, job: Job) -> None:
        self._fila = fila
        self._job = job
        self.lease_perdido = threading.Event()

    def verificar(self) -> None:
        if self.lease_perdido.is_set():
            raise LeasePerdido("lease perdido")
        if self._fila.cancelamento_solicitado(self._job.id):
            raise Cancelado("cancelamento solicitado")

    def progresso(self, dados: dict[str, Any]) -> None:
        self._fila.progresso(self._job.id, dados)


class Worker:
    def __init__(
        self,
        fila: FilaDeJobs,
        executor: ExecutorDeJobs,
        *,
        worker_id: str | None = None,
        lease_s: int = 600,
        heartbeat_s: float = 60,
        poll_min_s: float = 1.0,
        poll_max_s: float = 5.0,
        reaper_s: float = 60,
        periodicas: list[Callable[[], int]] | None = None,
    ) -> None:
        self.periodicas = periodicas or []
        self.fila = fila
        self.executor = executor
        self.id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease_s = lease_s
        self.heartbeat_s = heartbeat_s
        self.poll_min_s = poll_min_s
        self.poll_max_s = poll_max_s
        self.reaper_s = reaper_s
        self._ultimo_reaper = 0.0

    def _heartbeat(self, job: Job, controle: _Controle, fim: threading.Event) -> None:
        while not fim.wait(self.heartbeat_s):
            try:
                if not self.fila.renovar(job.id, self.id, self.lease_s):
                    controle.lease_perdido.set()
                    return
            except Exception:
                logger.exception("falha no heartbeat")

    def rodar_uma_vez(self) -> bool:
        """Processa no máximo um job. Devolve se havia trabalho."""
        agora = time.monotonic()
        if agora - self._ultimo_reaper >= self.reaper_s:
            self._ultimo_reaper = agora
            if devolvidos := self.fila.recolher_vencidos():
                logger.warning("jobs com lease vencido devolvidos", extra={"jobs": devolvidos})

        job = self.fila.reivindicar(self.id, self.lease_s)
        if job is None:
            return False
        token = job_id_var.set(str(job.id))
        controle, fim = _Controle(self.fila, job), threading.Event()
        batimento = threading.Thread(target=self._heartbeat, args=(job, controle, fim), daemon=True)
        batimento.start()
        inicio = time.perf_counter()
        try:
            resultado = self.executor.executar(job, controle)
            fim.set()
            self.fila.concluir(job.id, self.id, resultado)
            logger.info(
                "job concluído",
                extra={
                    "tipo": job.tipo.value,
                    "duracao_s": round(time.perf_counter() - inicio, 2),
                    **{f"r_{k}": v for k, v in resultado.items()},
                },
            )
        except LeasePerdido:
            logger.warning("lease perdido: outro worker assumiu o job")
        except Cancelado:
            self.fila.marcar_cancelado(job.id, self.id)
            logger.info("job cancelado")
        except Exception as exc:
            erro = f"{type(exc).__name__}: {exc}"
            status = self.fila.falhar(job.id, self.id, erro)
            logger.exception(
                "job falhou", extra={"status_novo": status, "tentativa": job.tentativas}
            )
            if status == "morto":
                self.executor.ao_desistir(job, erro)
        finally:
            fim.set()
            batimento.join(timeout=5)
            job_id_var.reset(token)
        return True

    def rodar(self, parar: threading.Event) -> None:
        espera = self.poll_min_s
        logger.info("worker iniciado", extra={"worker_id": self.id})
        while not parar.is_set():
            try:
                trabalhou = self.rodar_uma_vez()
            except Exception:
                logger.exception("erro no laço do worker")
                trabalhou = False
            for tarefa in self.periodicas:  # ex.: outbox de notificações
                try:
                    trabalhou = bool(tarefa()) or trabalhou
                except Exception:
                    logger.exception("erro em tarefa periódica")
            # Polling adaptativo: fila vazia -> espera cresce até poll_max.
            espera = self.poll_min_s if trabalhou else min(espera * 1.5, self.poll_max_s)
            if not trabalhou:
                parar.wait(espera)
        logger.info("worker encerrado")


def _a_cada(segundos: float, tarefa: Callable[[], int]) -> Callable[[], int]:
    proxima = [0.0]

    def rodar() -> int:
        if time.monotonic() < proxima[0]:
            return 0
        proxima[0] = time.monotonic() + segundos
        return tarefa()

    return rodar


def main() -> int:
    from sistemacampero.infrastructure.config import Settings
    from sistemacampero.infrastructure.container import construir
    from sistemacampero.infrastructure.logging_config import configurar_logs

    settings = Settings()
    configurar_logs(settings.log_level, settings.log_json)
    c = construir(settings)
    assert c.fila is not None and c.executor is not None
    contatos = c.contatos
    worker = Worker(
        c.fila,
        c.executor,
        lease_s=settings.worker_lease_s,
        heartbeat_s=settings.worker_heartbeat_s,
        poll_min_s=settings.worker_poll_min_s,
        poll_max_s=settings.worker_poll_max_s,
        periodicas=[
            *([c.notificacoes.enviar_pendentes] if c.notificacoes else []),
            *([_a_cada(3600, c.exportacao.limpar_vencidas)] if c.exportacao else []),
            *(
                [_a_cada(86400, lambda: contatos.expurgar(settings.retencao_contatos_meses))]
                if contatos
                else []
            ),
        ],
    )
    parar = threading.Event()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sinal, lambda *_: parar.set())
    try:
        worker.rodar(parar)
    finally:
        c.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
