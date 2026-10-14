"""Offset vs paginacion por llave (keyset) a 4,000,000 — version 2.

Mejoras sobre la v1:
  - el cursor de keyset se obtiene por busqueda binaria sobre el conteo exacto
    (`filter: SEG AND ts <= X` devuelve estimatedTotalHits exacto), de modo que
    la posicion del cursor es comparable 1:1 con el `offset` de la otra via;
  - se registra el codigo HTTP y si los hits coinciden con lo esperado;
  - se miden 20 repeticiones de keyset (el costo real de recorrer el segmento).

  python3 bench/keyset_vs_offset.py --port 7704
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

SCALE = 4_000_000
SEG = 'estatus_cuenta = "activo" AND dias_atraso = 0'
FIELD = "fecha_registro_ts"
T0, T1 = 1_672_531_200, 1_760_000_000
POSITIONS = [10_000, 100_000, 1_000_000]


def log(msg, fh=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n"); fh.flush()


def search(m, uid, body):
    st, j, w, n = m.fast.search(uid, body)
    return st, j or {}, w


def count_le(m, uid, x):
    st, j, _w = search(m, uid, {"filter": f"{SEG} AND {FIELD} <= {x}", "limit": 0})
    return j.get("estimatedTotalHits")


def cursor_for_position(m, uid, pos, fh):
    """Valor de FIELD tal que la cantidad de clientes del segmento con
    FIELD <= X sea ~pos (busqueda binaria sobre conteos exactos)."""
    lo, hi = T0, T1
    probes = 0
    while lo < hi:
        mid = (lo + hi) // 2
        c = count_le(m, uid, mid)
        probes += 1
        if c is None:
            return None, probes
        if c < pos:
            lo = mid + 1
        else:
            hi = mid
    log(f"    (cursor para pos {pos:,} encontrado en {probes} sondeos: {lo})", fh)
    return lo, probes


def probe(m, uid, body, reps, warm=1):
    for _ in range(warm):
        search(m, uid, body)
    walls, srv, status, hits = [], [], None, None
    for _ in range(reps):
        st, j, w = search(m, uid, body)
        status, hits = st, len(j.get("hits", []))
        if st == 200:
            walls.append(w)
            if j.get("processingTimeMs") is not None:
                srv.append(j["processingTimeMs"])
    if not walls:
        return {"reps": reps, "status": status, "hits": hits, "p50_ms": None, "error": True}
    return {"reps": reps, "status": status, "hits": hits,
            "p50_ms": round(C.pct(walls, 50), 2), "p95_ms": round(C.pct(walls, 95), 2),
            "meili_p50_ms": round(C.pct(srv, 50), 2) if srv else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7704)
    args = ap.parse_args()
    db = C.ROOT / "data" / "db" / str(SCALE)
    if not (db / "VERSION").exists():
        raise SystemExit(f"falta la base indexada en {db}")
    gt = json.loads((C.ROOT / "gen" / "ground_truth.json").read_text())
    gt_seg = gt["scales"][str(SCALE)]["queries"]["deep_activos_sin_atraso"]["count"]
    m = C.Meili(db, port=args.port, max_total_hits=SCALE, label=f"keyset{SCALE}")
    C.LOGS.mkdir(exist_ok=True)
    uid = spec.INDEX_UID
    with open(C.LOGS / "keyset_vs_offset.log", "a") as fh:
        ready = m.start()
        log(f"=== keyset vs offset v2 (escala {SCALE:,}) arranque {ready:.2f}s · segmento {gt_seg:,} ===", fh)
        out = {"scale": SCALE, "campo": FIELD, "filtro_segmento": SEG,
               "ground_truth_segmento": gt_seg, "posiciones": POSITIONS,
               "host": C.sysinfo(), "filas": []}
        try:
            for pos in POSITIONS:
                exp_hits = max(0, min(20, gt_seg - pos))
                off = probe(m, uid, {"filter": SEG, "sort": [f"{FIELD}:asc"],
                                     "offset": pos, "limit": 20}, reps=3)
                cur, probes = cursor_for_position(m, uid, pos, fh)
                key = probe(m, uid, {"filter": f"{SEG} AND {FIELD} > {cur}",
                                     "sort": [f"{FIELD}:asc"], "limit": 20}, reps=20)
                fila = {"posicion": pos, "hits_esperados": exp_hits, "cursor": cur,
                        "sondeos_binarios": probes, "por_offset": off, "por_keyset": key}
                if off.get("p50_ms") and key.get("p50_ms"):
                    fila["factor"] = round(off["p50_ms"] / key["p50_ms"], 1)
                fila["keyset_hits_ok"] = (key.get("hits") == exp_hits)
                fila["offset_hits_ok"] = (off.get("hits") == exp_hits)
                out["filas"].append(fila)
                log(f"  posicion {pos:>9,}: offset p50={off.get('p50_ms')} ms hits={off.get('hits')}"
                    f" (esperados {exp_hits}) | keyset p50={key.get('p50_ms')} ms hits={key.get('hits')}"
                    f" | factor {fila.get('factor')}x", fh)
        finally:
            m.stop()
    C.write_json(C.RAW / "keyset_vs_offset.json", out)
    print(f"escrito {C.RAW}/keyset_vs_offset.json")


if __name__ == "__main__":
    main()
