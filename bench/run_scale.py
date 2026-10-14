"""Corre una escala completa del laboratorio:
  load -> queries (cap default 1000) -> concurrencia -> subir maxTotalHits
  -> queries (sin cap) -> paginacion profunda

Uso:
  python3 bench/run_scale.py --scale 1000
  python3 bench/run_scale.py --scale 4000000 --stages load,queries_default
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
sys.path.insert(0, str(C.ROOT / "gen"))
import spec  # noqa: E402

GT = json.loads((C.ROOT / "gen" / "ground_truth.json").read_text())
REPS = 20
WARMUP = 3


def log(msg, fh=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n")
        fh.flush()


def fmt_num(v):
    return f"{v:8.2f}ms" if isinstance(v, (int, float)) else "     n/a"


def do_load(m: C.Meili, scale: int, batch: int, logfh):
    uid = spec.INDEX_UID
    m.create_index(uid)
    t_set = m.apply_settings(uid)
    log(f"settings aplicados en {t_set:.2f}s", logfh)
    mark = m.mark()
    t0 = time.time()
    batches_info = []
    sent = 0
    for buf in C.batches(scale, batch):
        body = "".join(buf).encode("utf-8")
        ts = time.time()
        r = m.http.post(f"{m.base}/indexes/{uid}/documents", data=body,
                        headers={"Content-Type": "application/x-ndjson"}, timeout=1800)
        r.raise_for_status()
        task = m.wait_task(r.json()["taskUid"])
        if task["status"] != "succeeded":
            raise RuntimeError(f"indexado fallo: {json.dumps(task)[:400]}")
        sent += len(buf)
        batches_info.append({"docs": len(buf), "bytes": len(body),
                             "s": round(time.time() - ts, 3),
                             "meili_ms": task.get("duration")})
        if len(batches_info) % max(1, (scale // batch) // 10 or 1) == 0:
            el = time.time() - t0
            log(f"  indexado {sent:,}/{scale:,} ({sent/el:,.0f} docs/s)", logfh)
    t_index = time.time() - t0
    stats = m.index_stats(uid)
    res = {
        "docs_solicitados": scale,
        "docs_indexados": stats.get("numberOfDocuments"),
        "settings_s": round(t_set, 3),
        "index_s": round(t_index, 3),
        "docs_per_s": round(sent / t_index, 1),
        "batch_size": batch,
        "n_batches": len(batches_info),
        "batch_stats": {
            "s_min": min(b["s"] for b in batches_info),
            "s_p50": round(statistics.median([b["s"] for b in batches_info]), 3),
            "s_max": max(b["s"] for b in batches_info),
        },
        "ndjson_bytes": sum(b["bytes"] for b in batches_info),
        "db_bytes": m.db_size_bytes(),
        "peak_rss_bytes": m.peak_rss_since(mark),
        "cpu": m.cpu_since(mark),
        "index_stats": stats,
    }
    res["db_bytes_per_doc"] = round(res["db_bytes"] / max(1, sent), 1)
    log(f"indexado completo: {sent:,} docs en {t_index:.1f}s "
        f"({res['docs_per_s']:,.0f} docs/s), db={res['db_bytes']/2**30:.2f} GiB, "
        f"pico RSS={res['peak_rss_bytes']/2**30:.2f} GiB", logfh)
    return res


def search_body(q: dict, extra: dict) -> dict:
    body = dict(q["body"])
    body.update(extra)
    return body


def run_query_once(m: C.Meili, uid: str, body: dict):
    status, j, wall, nbytes = m.fast.search(uid, body)
    if status != 200 or j is None:
        return {"error": status, "wall_ms": wall, "bytes": nbytes}
    return {"wall_ms": wall, "bytes": nbytes,
            "meili_ms": j.get("processingTimeMs"),
            "hits": len(j.get("hits", [])),
            "estimatedTotalHits": j.get("estimatedTotalHits"),
            "totalHits": j.get("totalHits"),
            "facetDistribution": j.get("facetDistribution"),
            "ids": [h.get("id") for h in j.get("hits", [])][:5]}


def measure(m: C.Meili, uid: str, body: dict, reps: int):
    samples = []
    last = None
    for _ in range(reps):
        last = run_query_once(m, uid, body)
        if "error" in last:
            return {"error": last["error"], "text": last.get("text")}
        samples.append(last)
    walls = [s["wall_ms"] for s in samples]
    meili = [s["meili_ms"] for s in samples if s["meili_ms"] is not None]
    return {
        "reps": reps,
        "wall_ms_p50": round(C.pct(walls, 50), 2),
        "wall_ms_p95": round(C.pct(walls, 95), 2),
        "wall_ms_p99": round(C.pct(walls, 99), 2),
        "wall_ms_min": round(min(walls), 2),
        "wall_ms_max": round(max(walls), 2),
        "meili_ms_p50": round(C.pct(meili, 50), 2) if meili else None,
        "meili_ms_p95": round(C.pct(meili, 95), 2) if meili else None,
        "hits": last["hits"],
        "estimatedTotalHits": last["estimatedTotalHits"],
        "totalHits": last["totalHits"],
        "resp_bytes": last["bytes"],
        "facetDistribution": last["facetDistribution"],
        "ids": last["ids"],
    }


NO_EXACT_TRUTH = set()


def compare_truth(q, res, scale, config):
    """Veredicto de correctitud contra el ground truth.

    Hallazgo medido (v1.55): `estimatedTotalHits` NO se recorta con
    `pagination.maxTotalHits`; devuelve el conteo real. Lo que el setting limita
    es cuantos hits se pueden extraer (offset+limit <= maxTotalHits). Por eso la
    expectativa es el conteo exacto en ambas configuraciones.
    """
    gt = GT["scales"][str(scale)]["queries"][q["id"]]
    truth = gt["count"]
    cap = 1000 if config == "default" else scale
    out = {"ground_truth_count": truth, "cap": cap, "expected_reported": truth}
    reported = res.get("estimatedTotalHits")
    if reported is None:
        reported = res.get("totalHits")
    out["reported"] = reported
    if q["id"] in NO_EXACT_TRUTH:
        out["count_match"] = None
    else:
        out["count_match"] = (reported == truth)
    if q["id"] in gt.get("facets", {}) or "facets" in q["body"]:
        got = res.get("facetDistribution") or {}
        exp = gt.get("facets", {})
        match = {}
        for field, counts in exp.items():
            g = got.get(field, {})
            match[field] = (len(g) == len(counts)) and all(
                int(g.get(k, -1)) == v for k, v in counts.items())
        out["facets_match"] = match
    return out


def client_overhead(m: C.Meili, uid: str, scale: int, logfh):
    """Cuanta latencia anade el cliente Python 'requests' frente a urllib3."""
    import requests  # noqa: F401
    body = dict(spec.QUERIES[9]["body"])
    body["limit"] = 20
    l1, l2 = [], []
    for _ in range(5):
        m.fast.search(uid, body)
        m.http.post(f"{m.base}/indexes/{uid}/search", json=body, timeout=120)
    for _ in range(30):
        l1.append(m.fast.search(uid, body)[2])
    for _ in range(30):
        t = time.perf_counter()
        m.http.post(f"{m.base}/indexes/{uid}/search", json=body, timeout=120)
        l2.append((time.perf_counter() - t) * 1000)
    out = {"urllib3_p50_ms": round(C.pct(l1, 50), 2), "urllib3_p95_ms": round(C.pct(l1, 95), 2),
           "requests_session_p50_ms": round(C.pct(l2, 50), 2),
           "requests_session_p95_ms": round(C.pct(l2, 95), 2)}
    out["delta_p50_ms"] = round(out["requests_session_p50_ms"] - out["urllib3_p50_ms"], 2)
    log(f"  [overhead] urllib3 p50={out['urllib3_p50_ms']}ms vs requests.Session "
        f"p50={out['requests_session_p50_ms']}ms (delta {out['delta_p50_ms']}ms)", logfh)
    return out


def verify_ids(m: C.Meili, uid: str, scale: int, logfh):
    """Comprueba que los documentos devueltos son realmente los del segmento:
    pide los 5 ids mas bajos (sort id:asc) y los compara con el ground truth."""
    gtsc = GT["scales"][str(scale)]["queries"]
    rows = []
    for q in spec.QUERIES:
        g = gtsc[q["id"]]
        if not g.get("sample_ids"):
            continue
        body = dict(q["body"])
        body.update({"limit": 5, "sort": ["id:asc"]})
        st, j, _w, _n = m.fast.search(uid, body)
        got = [h.get("id") for h in j.get("hits", [])] if j else None
        rows.append({"id": q["id"], "ok": (st == 200 and got == g["sample_ids"]),
                     "got": got, "esperado": g["sample_ids"]})
    oks = sum(1 for r in rows if r["ok"])
    log(f"  [verify_ids] {oks}/{len(rows)} segmentos devuelven exactamente los ids del ground truth", logfh)
    return {"ok": oks, "total": len(rows), "fallos": [r for r in rows if not r["ok"]]}


def typo_experiment(m: C.Meili, uid: str, scale: int, logfh):
    """Mide el efecto de la tolerancia a erratas sobre los conteos de texto."""
    txt = [q for q in spec.QUERIES if q["tipo"] == "search"]

    def run(mode: bool):
        t0 = time.time()
        r = m.http.patch(f"{m.base}/indexes/{uid}/settings",
                         json={"typoTolerance": {"enabled": mode}})
        m.wait_task(r.json()["taskUid"], timeout=7200)
        set_s = time.time() - t0
        qres = {}
        for q in txt:
            body = dict(q["body"])
            body["limit"] = 20
            for _ in range(2):
                run_query_once(m, uid, body)
            rm = measure(m, uid, body, max(6, REPS // 2))
            gt = GT["scales"][str(scale)]["queries"][q["id"]]["count"]
            rep = rm.get("estimatedTotalHits")
            qres[q["id"]] = {"p50_ms": rm.get("wall_ms_p50"), "reportado": rep,
                             "ground_truth_token_exacto": gt,
                             "factor_vs_exacto": (round(rep / gt, 3) if rep and gt else None)}
            log(f"  [typos={'on' if mode else 'off'}] {q['id']:36s} reportado={rep} "
                f"exacto={gt} factor={(round(rep/gt,3) if rep and gt else None)}", logfh)
        return {"settings_s": round(set_s, 3), "queries": qres}

    out = {"typos_on": run(True), "typos_off": run(False)}
    return out


def run_queries(m: C.Meili, uid: str, scale: int, config: str, limit_profile: int, logfh):
    mark = m.mark()
    reps = REPS if limit_profile <= 20 else max(6, REPS // 3)
    warm = 2 if limit_profile <= 20 else 1
    per_query = {}
    for q in spec.QUERIES:
        body = search_body(q, {"limit": limit_profile})
        for _ in range(warm):
            run_query_once(m, uid, body)
        res = measure(m, uid, body, reps)
        if "error" in res:
            per_query[q["id"]] = {"error": res}
            continue
        per_query[q["id"]] = {
            "tipo": q["tipo"], "desc": q["desc"],
            "metrics": {k: v for k, v in res.items() if k not in ("ids", "facetDistribution")},
            "truth_check": compare_truth(q, res, scale, config),
            "ids": res["ids"],
        }
        log(f"  [{config}/lim{limit_profile}] {q['id']:38s} p50={res['wall_ms_p50']:8.2f}ms "
            f"p95={res['wall_ms_p95']:8.2f}ms hits={res['hits']:5d} "
            f"reported={res['estimatedTotalHits'] or res['totalHits']}", logfh)
    return {"config": config, "limit": limit_profile, "reps": reps,
            "peak_rss_bytes": m.peak_rss_since(mark), "cpu": m.cpu_since(mark),
            "queries": per_query}


def raise_cap(m: C.Meili, scale: int, logfh):
    uid = spec.INDEX_UID
    mark = m.mark()
    t0 = time.time()
    r = m.http.patch(f"{m.base}/indexes/{uid}/settings",
                     json={"pagination": {"maxTotalHits": scale}}, timeout=60)
    r.raise_for_status()
    task = m.wait_task(r.json()["taskUid"], timeout=7200)
    dt = time.time() - t0
    log(f"maxTotalHits={scale} aplicado en {dt:.2f}s (status={task['status']}, "
        f"duration={task.get('duration')})", logfh)
    return {"raise_cap_s": round(dt, 3), "task_duration": task.get("duration"),
            "status": task["status"], "peak_rss_bytes": m.peak_rss_since(mark),
            "cpu": m.cpu_since(mark)}


def deep_pagination(m: C.Meili, uid: str, scale: int, logfh, reps: int | None = None,
                    offsets: list | None = None):
    mark = m.mark()
    reps = reps or max(6, REPS // 2)
    rows = []
    for entry in spec.DEEP_PAGINATION:
        for off in (offsets or spec.MAX_OFFSETS):
            body = dict(entry["body"])
            body.update({"offset": off, "limit": 20, "sort": ["id:asc"]})
            for _ in range(2):
                run_query_once(m, uid, body)
            res = measure(m, uid, body, reps)
            row = {"id": entry["id"], "offset": off, **{k: res.get(k) for k in
                   ("wall_ms_p50", "wall_ms_p95", "wall_ms_p99", "meili_ms_p50",
                    "hits", "totalHits", "estimatedTotalHits", "resp_bytes")}}
            if isinstance(res, dict) and not res.get("error"):
                gt = GT["scales"][str(scale)]["queries"][entry["id"]]["count"]
                row["ground_truth_count"] = gt
                row["expected_hits"] = max(0, min(20, gt - off))
                row["hits_ok"] = (row["hits"] == row["expected_hits"])
                row["total_ok"] = (res.get("totalHits") == gt or res.get("estimatedTotalHits") == gt)
            rows.append(row)
            log(f"  [deep/{entry['id']}] offset={off:>9,} p50={fmt_num(row['wall_ms_p50'])} "
                f"p95={fmt_num(row['wall_ms_p95'])} hits={row['hits']} "
                f"(esperado {row.get('expected_hits')})", logfh)
    return {"peak_rss_bytes": m.peak_rss_since(mark), "cpu": m.cpu_since(mark), "rows": rows}


def concurrency(m: C.Meili, uid: str, scale: int, clients, seconds, logfh):
    import threading
    mix = [q for q in spec.QUERIES if q["tipo"] in ("filter", "facet", "search")]
    out = []
    for ncli in clients:
        mark = m.mark()
        lock = threading.Lock()
        lat = []
        errors = []
        stop_at = time.time() + seconds

        def worker():
            while time.time() < stop_at:
                for q in mix:
                    if time.time() >= stop_at:
                        break
                    status, j, dt, _n = m.fast.search(uid, search_body(q, {"limit": 20}), 
                                                      timeout=120)
                    with lock:
                        if status == 200 and j is not None:
                            lat.append(dt)
                        else:
                            errors.append(f"http {status}")

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(ncli)]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.time() - t0
        row = {"clients": ncli, "wall_s": round(wall, 2), "requests": len(lat) + len(errors),
               "ok": len(lat), "errors": len(errors),
               "qps": round(len(lat) / wall, 1),
               "lat_p50": round(C.pct(lat, 50), 2) if lat else None,
               "lat_p90": round(C.pct(lat, 90), 2) if lat else None,
               "lat_p95": round(C.pct(lat, 95), 2) if lat else None,
               "lat_p99": round(C.pct(lat, 99), 2) if lat else None,
               "lat_max": round(max(lat), 2) if lat else None,
               "peak_rss_bytes": m.peak_rss_since(mark), "cpu": m.cpu_since(mark),
               "sample_error": errors[:2]}
        out.append(row)
        log(f"  [conc] clientes={ncli:3d} qps={row['qps']:8.1f} p50={row['lat_p50']}ms "
            f"p95={row['lat_p95']}ms err={row['errors']} cpu_max={row['cpu'].get('cpu_pct_max')}%", logfh)
    return out


def main():
    global REPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, required=True)
    ap.add_argument("--stages", default="load,queries_default,concurrency,raise_cap,queries_raised,verify_ids,typo_experiment,deep")
    ap.add_argument("--batch", type=int, default=20000)
    ap.add_argument("--port", type=int, default=7700)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--memory", default="4GiB")
    ap.add_argument("--keep-db", action="store_true")
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--clients", default="1,8,32,64")
    ap.add_argument("--deep-reps", type=int, default=0, help="repeticiones de paginacion profunda (0 = auto)")
    ap.add_argument("--deep-offsets", default="", help="offsets de paginacion profunda, ej. 0,100000,1000000")
    ap.add_argument("--conc-seconds", type=int, default=15)
    args = ap.parse_args()
    REPS = args.reps

    scale = args.scale
    stages = [s for s in args.stages.split(",") if s]
    C.RAW.mkdir(parents=True, exist_ok=True)
    out_path = C.RAW / f"scale_{scale}.json"
    logpath = C.LOGS / f"run_scale_{scale}.log"
    C.LOGS.mkdir(exist_ok=True)

    db = C.ROOT / "data" / "db" / str(scale)
    if not (args.keep_db and (db / "VERSION").exists()) and "load" in stages:
        shutil.rmtree(db, ignore_errors=True)

    m = C.Meili(db, port=args.port, threads=args.threads, memory=args.memory,
                max_total_hits=1000, label=f"{scale}")
    result = {"scale": scale, "host": C.sysinfo(), "flags": vars(args)}

    with open(logpath, "a") as logfh:
        log(f"=== escala {scale:,} stages={stages} ===", logfh)
        t_ready = m.start()
        result["startup_s"] = round(t_ready, 3)
        log(f"servidor listo en {t_ready:.2f}s (pid={m.proc.pid})", logfh)
        try:
            uid = spec.INDEX_UID
            if "load" in stages:
                result["load"] = do_load(m, scale, args.batch, logfh)
            else:
                result["load"] = {"reusado": True,
                                  "docs_indexados": m.index_stats(uid).get("numberOfDocuments"),
                                  "db_bytes": m.db_size_bytes()}
            if "queries_default" in stages:
                result["overhead_cliente"] = client_overhead(m, uid, scale, logfh)
                result["queries_default_limit20"] = run_queries(m, uid, scale, "default", 20, logfh)
                result["queries_default_limit1000"] = run_queries(m, uid, scale, "default", 1000, logfh)
            if "concurrency" in stages:
                clients = [int(c) for c in args.clients.split(",")]
                result["concurrency_default"] = concurrency(m, uid, scale, clients,
                                                            args.conc_seconds, logfh)
            if "raise_cap" in stages:
                result["raise_cap"] = raise_cap(m, scale, logfh)
            if "queries_raised" in stages:
                result["queries_raised_limit20"] = run_queries(m, uid, scale, "raised", 20, logfh)
                result["queries_raised_limit1000"] = run_queries(m, uid, scale, "raised", 1000, logfh)
            if "verify_ids" in stages:
                result["verify_ids"] = verify_ids(m, uid, scale, logfh)
            if "typo_experiment" in stages:
                result["typo_experiment"] = typo_experiment(m, uid, scale, logfh)
            if "deep" in stages:
                offs = [int(x) for x in args.deep_offsets.split(",") if x] or None
                result["deep_pagination"] = deep_pagination(
                    m, uid, scale, logfh, reps=(args.deep_reps or None), offsets=offs)
            result["final_db_bytes"] = m.db_size_bytes()
            result["peak_rss_bytes_total"] = m.peak_rss()
        finally:
            m.stop()
            if not args.keep_db and scale <= 10_000:
                shutil.rmtree(db, ignore_errors=True)
        if out_path.exists():
            prev = json.loads(out_path.read_text())
            for k in ("load", "overhead_cliente", "queries_default_limit20",
                      "queries_default_limit1000", "concurrency_default", "raise_cap",
                      "queries_raised_limit20", "queries_raised_limit1000", "verify_ids",
                      "typo_experiment", "deep_pagination"):
                if k not in result and k in prev:
                    result[k] = prev[k]
        C.write_json(out_path, result)
        log(f"=== escala {scale:,} terminada -> {out_path} ===", logfh)


if __name__ == "__main__":
    main()
