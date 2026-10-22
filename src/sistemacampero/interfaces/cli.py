"""CLI: ``sistemacampero db migrar`` e ``sistemacampero api``."""

from __future__ import annotations

import argparse
import os
import sys

from sistemacampero.infrastructure.logging_config import configurar_logs


def _dsn(args: argparse.Namespace) -> str:
    dsn = args.database_url or os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("Informe --database-url ou a variável DATABASE_URL.")
    return str(dsn)


def _migrar(args: argparse.Namespace) -> int:
    from sistemacampero.infrastructure.persistence import migrations

    dsn = _dsn(args)
    if args.criar_banco:
        migrations.criar_banco_se_preciso(dsn)
    feitas = migrations.aplicar(dsn, bootstrap=args.bootstrap)
    if args.senha_backend_local:
        senha = os.environ.get("CAMPERO_BACKEND_SENHA")
        if not senha:
            sys.exit("--senha-backend-local exige a variável CAMPERO_BACKEND_SENHA.")
        migrations.definir_senha_backend(dsn, senha)
    print(f"{len(feitas)} migration(s) aplicada(s): {', '.join(feitas) or '-'}")
    return 0


def _api(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "sistemacampero.interfaces.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
    )
    return 0


def _worker(_: argparse.Namespace) -> int:
    from sistemacampero.interfaces.worker import main as worker_main

    return worker_main()


def main(argv: list[str] | None = None) -> int:
    configurar_logs(os.environ.get("LOG_LEVEL", "INFO"), json_=False)
    parser = argparse.ArgumentParser(prog="sistemacampero")
    sub = parser.add_subparsers(dest="comando", required=True)

    db = sub.add_parser("db", help="banco de dados").add_subparsers(dest="acao", required=True)
    migrar = db.add_parser("migrar", help="aplica supabase/migrations pendentes")
    migrar.add_argument("--database-url")
    migrar.add_argument(
        "--bootstrap",
        action="store_true",
        help="cria papéis/schemas do Supabase num PostGIS comum (só dev/teste)",
    )
    migrar.add_argument("--criar-banco", action="store_true", help="cria o banco se não existir")
    migrar.add_argument(
        "--senha-backend-local",
        action="store_true",
        help="define a senha de campero_backend com CAMPERO_BACKEND_SENHA (só dev/teste)",
    )
    migrar.set_defaults(func=_migrar)

    api = sub.add_parser("api", help="sobe a API (uvicorn)")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    api.add_argument("--reload", action="store_true")
    api.set_defaults(func=_api)

    sub.add_parser("worker", help="processa a fila de jobs").set_defaults(func=_worker)

    args = parser.parse_args(argv)
    resultado: int = args.func(args)
    return resultado


if __name__ == "__main__":
    raise SystemExit(main())
