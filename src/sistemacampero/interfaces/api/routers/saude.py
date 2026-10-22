"""Saúde: ``/health`` (processo vivo), ``/ready`` (dependências) e ``/metrics``."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sistemacampero import __version__
from sistemacampero.interfaces.api.deps import ContainerDep

router = APIRouter(tags=["saúde"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "versao": __version__}


@router.get("/ready")
def ready(c: ContainerDep) -> JSONResponse:
    checks = c.prontidao.verificar()
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if ok else "indisponivel", "checks": checks},
        status_code=200 if ok else 503,
    )


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    registry = request.app.state.metricas.registry
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
