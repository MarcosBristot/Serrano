"""Regressão com dado real: processa um dump de pendrive e compara com a linha de base.

    uv run python scripts/regressao_dump.py "<pasta JD-Data/log>"              # compara
    uv run python scripts/regressao_dump.py "<pasta>" --congelar               # grava nova base
    uv run python scripts/regressao_dump.py "<pasta>" --saida ../saida_dump    # + CSV por sessão

O dump NÃO vai para o Git (dado de cliente). A linha de base guarda só números por
sha256 do arquivo, sem nomes de produtor, fazenda ou talhão. O CSV de --saida contém
nomes de arquivo: grave-o fora do repositório.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

BASE_PADRAO = Path(__file__).parent / "linha_base" / "subconjunto_2026.json"
CAMPOS_METRICAS = (
    "duracao_h",
    "motor_h",
    "trabalho_h",
    "ocioso_h",
    "delta_horimetro_h",
    "litros_integral",
    "litros_contador",
    "distancia_trabalho_km",
    "area_estimada_ha",
    "l_ha",
    "ha_h",
    "cobertura_gps",
)


def _r(v: float | None, casas: int = 4) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, casas)


def processar(caminho: str) -> dict[str, Any]:
    from sistemacampero.application.processamento import ProcessadorDeArquivo
    from sistemacampero.domain.errors import ErroDominio
    from sistemacampero.domain.telemetry import EmptyFile, ParseContext
    from sistemacampero.infrastructure.parsers.registry import registro_padrao

    p = Path(caminho)
    dados = p.read_bytes()
    base: dict[str, Any] = {"arquivo": p.name, "pasta": p.parent.name, "bytes": len(dados)}
    try:
        r = ProcessadorDeArquivo(registro_padrao()).processar(dados, ParseContext(p.name))
    except ErroDominio as exc:
        import hashlib

        return base | {
            "sha256": hashlib.sha256(dados).hexdigest(),
            "status": "erro",
            "motivo": exc.codigo,
        }
    if isinstance(r, EmptyFile):
        return base | {"sha256": r.sha256, "status": "vazio", "motivo": r.motivo}
    m = r.metricas
    return base | {
        "sha256": r.sessao.sha256,
        "status": "processado",
        "inicio": r.sessao.metadados.inicio.isoformat(),
        "fonte_posicao": r.sessao.diagnostico.fonte_posicao,
        "ancoras_divergentes": r.sessao.diagnostico.contadores.get("ancoras_divergentes", 0),
        "qualidade": r.qualidade.score,
        "problemas": sorted(p_.codigo for p_ in r.qualidade.problemas),
        "alertas": dict(Counter(a.tipo for a in r.alertas)),
        "metricas": {c: _r(getattr(m, c)) for c in CAMPOS_METRICAS} if m else {},
    }


def resumir(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    proc = [x for x in linhas if x["status"] == "processado"]

    def soma(c: str) -> float:
        return round(sum(x["metricas"].get(c) or 0 for x in proc), 1)

    def mediana(c: str) -> float | None:
        vals = [x["metricas"][c] for x in proc if x["metricas"].get(c) is not None]
        return round(statistics.median(vals), 3) if vals else None

    pares = [
        x["metricas"]["litros_contador"] / x["metricas"]["litros_integral"]
        for x in proc
        if (x["metricas"].get("litros_contador") or 0) >= 10
        and (x["metricas"].get("litros_integral") or 0) > 0
        and (x["metricas"].get("motor_h") or 0) >= 0.5
    ]
    alertas: Counter[str] = Counter()
    problemas: Counter[str] = Counter()
    for x in proc:
        alertas.update(x["alertas"])
        problemas.update(x["problemas"])
    return {
        "arquivos": len(linhas),
        "status": dict(Counter(x["status"] for x in linhas)),
        "motivos_vazio": dict(Counter(x["motivo"] for x in linhas if x["status"] != "processado")),
        "fonte_posicao": dict(Counter(x["fonte_posicao"] for x in proc)),
        "motor_h": soma("motor_h"),
        "trabalho_h": soma("trabalho_h"),
        "ocioso_h": soma("ocioso_h"),
        "delta_horimetro_h": soma("delta_horimetro_h"),
        "litros_integral": soma("litros_integral"),
        "litros_contador": soma("litros_contador"),
        "area_estimada_ha": soma("area_estimada_ha"),
        "mediana_l_ha": mediana("l_ha"),
        "mediana_ha_h": mediana("ha_h"),
        "contador_sobre_integral": {
            "sessoes": len(pares),
            "mediana": round(statistics.median(pares), 3) if pares else None,
        },
        "sessoes_com_gps": sum(1 for x in proc if (x["metricas"].get("cobertura_gps") or 0) > 0),
        "ancoras_divergentes": sum(x["ancoras_divergentes"] for x in proc),
        "qualidade_mediana": statistics.median([x["qualidade"] for x in proc]) if proc else None,
        "problemas": dict(sorted(problemas.items())),
        "alertas": dict(sorted(alertas.items())),
    }


def _versoes() -> dict[str, str]:
    from sistemacampero.domain.services.rules import ConfigRegras
    from sistemacampero.domain.services.sanitization import SANITIZER_VERSION
    from sistemacampero.infrastructure.parsers.john_deere_gen4.adapter import VERSAO

    return {"adapter": VERSAO, "sanitizador": SANITIZER_VERSION, "regras": ConfigRegras().versao}


def _para_base(x: dict[str, Any]) -> dict[str, Any]:
    """Só números e códigos: nada de nome de arquivo/pasta (têm nome de produtor)."""
    return {k: v for k, v in x.items() if k not in ("arquivo", "pasta", "bytes")}


def comparar(atual: dict[str, Any], base: dict[str, Any]) -> list[str]:
    difs = []
    for sha, ref in base["sessoes"].items():
        cur = atual.get(sha)
        if cur is None:
            difs.append(f"{sha[:12]} ausente no dump atual")
            continue
        for chave in ("status", "motivo", "fonte_posicao", "problemas", "alertas"):
            if cur.get(chave) != ref.get(chave):
                difs.append(f"{sha[:12]} {chave}: {ref.get(chave)} -> {cur.get(chave)}")
        for c, v in (ref.get("metricas") or {}).items():
            w = (cur.get("metricas") or {}).get(c)
            if (v is None) != (w is None) or (
                v is not None
                and w is not None
                and not math.isclose(v, w, rel_tol=1e-4, abs_tol=1e-3)
            ):
                difs.append(f"{sha[:12]} {c}: {v} -> {w}")
    return difs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--linha-base", type=Path, default=BASE_PADRAO)
    ap.add_argument("--congelar", action="store_true", help="grava a linha de base atual")
    ap.add_argument("--saida", type=Path, help="pasta (fora do Git) para o CSV por sessão")
    ap.add_argument("--processos", type=int, default=4)
    args = ap.parse_args()

    arquivos = sorted(str(p) for p in args.pasta.rglob("*.jdl"))
    if not arquivos:
        print("nenhum .jdl encontrado", file=sys.stderr)
        return 2
    inicio = time.perf_counter()
    with ProcessPoolExecutor(args.processos) as ex:
        linhas = list(ex.map(processar, arquivos, chunksize=8))
    duracao = time.perf_counter() - inicio
    resumo = resumir(linhas)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"\n{len(arquivos)} arquivos em {duracao:.1f} s ({args.processos} processos)")

    if args.saida:
        import csv

        args.saida.mkdir(parents=True, exist_ok=True)
        destino = args.saida / "sessoes.csv"
        with destino.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "pasta",
                    "arquivo",
                    "sha256",
                    "status",
                    "motivo",
                    "qualidade",
                    "problemas",
                    "alertas",
                    *CAMPOS_METRICAS,
                ]
            )
            for x in linhas:
                m = x.get("metricas") or {}
                w.writerow(
                    [
                        x["pasta"],
                        x["arquivo"],
                        x["sha256"],
                        x["status"],
                        x.get("motivo"),
                        x.get("qualidade"),
                        ";".join(x.get("problemas", [])),
                        json.dumps(x.get("alertas", {})),
                        *(m.get(c) for c in CAMPOS_METRICAS),
                    ]
                )
        print(f"CSV por sessão: {destino}")

    atual = {x["sha256"]: _para_base(x) for x in linhas}
    if args.congelar:
        args.linha_base.parent.mkdir(parents=True, exist_ok=True)
        conteudo = {"versoes": _versoes(), "resumo": resumo, "sessoes": dict(sorted(atual.items()))}
        args.linha_base.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"linha de base congelada em {args.linha_base}")
        return 0
    if not args.linha_base.exists():
        print("sem linha de base para comparar (use --congelar)")
        return 0
    base = json.loads(args.linha_base.read_text(encoding="utf-8"))
    difs = comparar(atual, base)
    if base["versoes"] != _versoes():
        print(f"versões mudaram: {base['versoes']} -> {_versoes()}")
    if difs:
        print(f"\n{len(difs)} diferença(s) em relação à linha de base:")
        print("\n".join(difs[:50]))
        return 1
    print("\nsem diferenças em relação à linha de base")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
