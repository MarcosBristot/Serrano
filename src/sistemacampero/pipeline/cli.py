"""CLI:  python -m sistemacampero.pipeline.cli ingest <pasta> --workdir ./saida
        python -m sistemacampero.pipeline.cli analyze --workdir ./saida"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sistemacampero.pipeline.runner import analyze, ingest_paths


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="sistemacampero")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ingest", help="etapas 1-3 (bruto -> limpo)")
    a.add_argument("folder", type=Path)
    a.add_argument("--workdir", type=Path, required=True)
    a.add_argument("--workers", type=int, default=4)
    b = sub.add_parser("analyze", help="etapas 4-5 (métricas + alertas)")
    b.add_argument("--workdir", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        files = sorted(args.folder.rglob("*.jdl"))
        res = ingest_paths(files, args.workdir, args.workers)
        print(dict(Counter(r["status"] for r in res)))
        errs = [r for r in res if r["status"] == "erro"]
        for e in errs[:10]:
            print("ERRO", e["file"], e["reason"])
    else:
        print(json.dumps(analyze(args.workdir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
