"""Autochequeo del laboratorio: valida los invariantes que sostienen el reporte.

  python3 bench/selfcheck.py

Falla (exit 1) si alguna escala no cumple:
  - todos los documentos enviados quedaron indexados,
  - 0 discrepancias de conteo contra el ground truth en las 4 variantes medidas,
  - facetas identicas al ground truth,
  - ids devueltos identicos al ground truth,
  - ninguna consulta con error HTTP,
  - paginacion profunda sin hits inesperados.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen"))
import spec  # noqa: E402

RAW = ROOT / "raw"
GT = json.loads((ROOT / "gen" / "ground_truth.json").read_text())
TEXTS = ("queries_default_limit20", "queries_default_limit1000",
         "queries_raised_limit20", "queries_raised_limit1000")

fails: list[str] = []
lines: list[str] = []


def check(cond, msg):
    lines.append(("OK   " if cond else "FALLA") + "  " + msg)
    if not cond:
        fails.append(msg)


present = []
for sc in spec.SCALES:
    p = RAW / f"scale_{sc}.json"
    if p.exists():
        present.append((sc, json.loads(p.read_text())))
    else:
        check(False, f"falta raw/scale_{sc}.json")

for sc, d in present:
    load = d.get("load", {})
    check(load.get("docs_indexados") == sc,
          f"{sc:,}: documentos indexados {load.get('docs_indexados')} == {sc:,}")
    check(bool(load.get("docs_per_s")), f"{sc:,}: throughput de indexado registrado")

    for key in TEXTS:
        st = d.get(key)
        if not st:
            check(False, f"{sc:,}: falta la etapa {key}")
            continue
        errs = [q for q, v in st["queries"].items() if "error" in v]
        check(not errs, f"{sc:,}/{key}: sin errores HTTP ({len(errs)} errores)")
        mism = []
        for qid, qv in st["queries"].items():
            if "metrics" not in qv:
                continue
            tc = qv.get("truth_check") or {}
            gt = GT["scales"][str(sc)]["queries"][qid]["count"]
            rep = (qv["metrics"].get("estimatedTotalHits")
                   if qv["metrics"].get("estimatedTotalHits") is not None
                   else qv["metrics"].get("totalHits"))
            if rep != gt:
                mism.append(f"{qid}(reportado {rep} != GT {gt})")
            fm = tc.get("facets_match")
            if fm and not all(fm.values()):
                mism.append(qid + "(facets)")
        check(not mism, f"{sc:,}/{key}: conteos y facetas == ground truth ({len(mism)} discrepancias)")

    vi = d.get("verify_ids")
    if vi:
        check(vi["ok"] == vi["total"], f"{sc:,}: ids devueltos == ground truth ({vi['ok']}/{vi['total']})")
    else:
        check(False, f"{sc:,}: falta verify_ids")

    for row in d.get("concurrency_default", []):
        check(row["errors"] == 0, f"{sc:,}: concurrencia {row['clients']} clientes sin errores")

    dp = d.get("deep_pagination", {}).get("rows", [])
    bad = [r for r in dp if r.get("hits_ok") is False]
    check(not bad, f"{sc:,}: paginacion profunda con hits esperados ({len(bad)} fallos)")
    check(all(r.get("total_ok") for r in dp) if dp else True,
          f"{sc:,}: total de paginacion profunda == ground truth")

ver = RAW / "verificacion_ndjson.json"
if ver.exists():
    r = json.loads(ver.read_text())["resumen"]
    check(r["discrepancias"] == 0 and r["docs_totales"] == spec.TOTAL,
          f"NDJSON vs ground truth: {r['ok']}/{r['comparaciones']} ok, {r['docs_totales']:,} docs")

print("\n".join(lines))
print()
print(f"{'TODO OK' if not fails else str(len(fails)) + ' FALLOS'}: "
      f"{len(present)} escalas verificadas")
sys.exit(1 if fails else 0)
