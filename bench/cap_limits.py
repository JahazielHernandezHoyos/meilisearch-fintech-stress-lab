"""Experimento de la semantica de `pagination.maxTotalHits`.

Responde, contra datos ya indexados (no reindexa):
  1. ¿`estimatedTotalHits` se recorta con maxTotalHits?  -> no (conteo real)
  2. ¿Se puede pedir limit > 1000?
  3. ¿offset + limit puede pasar de maxTotalHits?
  4. ¿La paginacion por page/hitsPerPage topa `totalHits`?
  5. ¿Cual es el conteo exacto del segmento (ground truth) en cada modo?

  python3 bench/cap_limits.py --scale 1000000 --port 7702
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
sys.path.insert(0, str(C.ROOT / "gen"))
import spec  # noqa: E402

GT = json.loads((C.ROOT / "gen" / "ground_truth.json").read_text())


def log(msg, fh=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n")
        fh.flush()


def probe(m, uid, body):
    st, j, wall, n = m.fast.search(uid, body)
    out = {"body": body, "status": st, "wall_ms": round(wall, 2), "bytes": n}
    if st == 200 and j is not None:
        out.update({"hits": len(j.get("hits", [])),
                    "estimatedTotalHits": j.get("estimatedTotalHits"),
                    "totalHits": j.get("totalHits"),
                    "totalPages": j.get("totalPages"),
                    "page": j.get("page")})
    else:
        out["error"] = (j or {}).get("message", "")[:160] if isinstance(j, dict) else str(j)[:160]
    return out


def run_for_cap(m, uid, scale, cap, label, logfh):
    r = m.http.patch(f"{m.base}/indexes/{uid}/settings",
                     json={"pagination": {"maxTotalHits": cap}})
    m.wait_task(r.json()["taskUid"], timeout=7200)
    seg = {"filter": 'estatus_cuenta = "activo" AND dias_atraso = 0'}
    truth = GT["scales"][str(scale)]["queries"]["deep_activos_sin_atraso"]["count"]
    rows = []
    cases = [
        ("limit=20", {**seg, "limit": 20}),
        ("limit=1000", {**seg, "limit": 1000}),
        ("limit=1001", {**seg, "limit": 1001}),
        ("limit=5000", {**seg, "limit": 5000}),
        ("offset=900&limit=20", {**seg, "offset": 900, "limit": 20}),
        ("offset=990&limit=20 (=1000)", {**seg, "offset": 990, "limit": 20}),
        ("offset=1000&limit=20", {**seg, "offset": 1000, "limit": 20}),
        ("offset=100000&limit=20", {**seg, "offset": 100000, "limit": 20}),
        ("page=50&hitsPerPage=20 (=1000)", {**seg, "page": 50, "hitsPerPage": 20}),
        ("page=51&hitsPerPage=20 (>1000)", {**seg, "page": 51, "hitsPerPage": 20}),
        ("page=1&hitsPerPage=100", {**seg, "page": 1, "hitsPerPage": 100}),
    ]
    for name, body in cases:
        row = {"caso": name, **probe(m, uid, body), "ground_truth_segmento": truth}
        rows.append(row)
        log(f"  [cap={cap:,}] {name:34s} http={row['status']} hits={row.get('hits')} "
            f"estimated={row.get('estimatedTotalHits')} total={row.get('totalHits')} "
            f"{row.get('error','')}", logfh)
    return {"maxTotalHits": cap, "label": label, "ground_truth_segmento": truth, "casos": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1_000_000)
    ap.add_argument("--port", type=int, default=7702)
    ap.add_argument("--caps", default="1000,1000000")
    args = ap.parse_args()
    db = C.ROOT / "data" / "db" / str(args.scale)
    if not (db / "VERSION").exists():
        raise SystemExit(f"no existe la base indexada en {db}")
    m = C.Meili(db, port=args.port, max_total_hits=10**9, label=f"caplimits{args.scale}")
    C.LOGS.mkdir(exist_ok=True)
    with open(C.LOGS / f"cap_limits_{args.scale}.log", "a") as logfh:
        ready = m.start()
        log(f"=== cap_limits escala={args.scale} (arranque {ready:.2f}s) ===", logfh)
        uid = spec.INDEX_UID
        out = {"scale": args.scale, "host": C.sysinfo(),
               "docs": m.index_stats(uid).get("numberOfDocuments")}
        try:
            out["corridas"] = [run_for_cap(m, uid, args.scale, int(c), f"cap={c}", logfh)
                               for c in args.caps.split(",")]
        finally:
            m.stop()
    C.write_json(C.RAW / f"cap_limits_{args.scale}.json", out)
    print(f"escrito {C.RAW}/cap_limits_{args.scale}.json")


if __name__ == "__main__":
    main()
