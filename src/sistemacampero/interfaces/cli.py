"""Linha de comando: ingestão em lote, análise, publicação, talhões e servidor.

sistemacampero ingest  <pasta JD-Data/log>
sistemacampero analyze
sistemacampero publish
sistemacampero import-boundaries <pasta Gen4>
sistemacampero serve
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import build_services
from sistemacampero.infrastructure.parsers.john_deere_gen4.spatial import (
    SpatialFilesFieldSource,
)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sistemacampero")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ingest = sub.add_parser("ingest", help="etapas 1-3: bruto -> limpo")
    ingest.add_argument("folder", type=Path)
    ingest.add_argument("--workers", type=int, default=1)
    sub.add_parser("analyze", help="etapas 4-5: métricas + alertas (reprocessável)")
    sub.add_parser("publish", help="publica no Supabase o que ainda não foi publicado")
    bounds = sub.add_parser("import-boundaries", help="importa talhões (contornos) para o Supabase")
    bounds.add_argument("gen4_dir", type=Path, help="pasta Gen4 com MasterData.xml e SpatialFiles")
    bounds.add_argument("--dry-run", action="store_true", help="só lista, sem gravar")
    serve = sub.add_parser("serve", help="sobe a API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return ap


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parser().parse_args(argv)
    services = build_services(Settings.from_env())

    if args.cmd == "ingest":
        files = sorted(args.folder.rglob("*.jdl"))
        results = services.ingestion.ingest_many(files, args.workers)
        print(dict(Counter(r.status for r in results)))
        for err in [r for r in results if r.status == "erro"][:10]:
            print("ERRO", err.file, (err.reason or "").splitlines()[0])
        return 1 if any(r.status == "erro" for r in results) else 0

    if args.cmd == "analyze":
        print(json.dumps(services.analysis.analyze_all(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "publish":
        print(json.dumps(services.processor.publish_pending(), ensure_ascii=False))
        return 0

    if args.cmd == "import-boundaries":
        fields = SpatialFilesFieldSource(args.gen4_dir).list_fields()
        for f in fields:
            print(f"{f.name:<20} {f.area_ha:>8.1f} ha  {f.farm or '-'}")
        if args.dry_run:
            return 0
        if services.field_repository is None:
            print("Supabase não configurado (SUPABASE_URL/SUPABASE_KEY).", file=sys.stderr)
            return 2
        print(f"{services.field_repository.upsert_fields(fields)} talhões gravados.")
        return 0

    import uvicorn

    uvicorn.run(
        "sistemacampero.interfaces.api.main:app", host=args.host, port=args.port, factory=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
