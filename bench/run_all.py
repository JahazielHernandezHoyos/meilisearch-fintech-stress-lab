"""Orquesta todas las escalas del laboratorio, de menor a mayor.

  python3 bench/run_all.py                  # todas las escalas completas
  python3 bench/run_all.py --scales 1000,3000
  python3 bench/run_all.py --stages load,queries_default

Cada escala corre en un proceso aparte (bench/run_scale.py) para que un fallo
no tumbe el resto; los resultados quedan en raw/scale_<N>.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen"))
import spec  # noqa: E402

PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default=",".join(str(s) for s in spec.SCALES))
    ap.add_argument("--stages", default="load,queries_default,concurrency,raise_cap,queries_raised,verify_ids,typo_experiment,deep")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--batch", type=int, default=20000)
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args()

    scales = [int(s) for s in args.scales.split(",") if s]
    logpath = ROOT / "logs" / "run_all.log"
    logpath.parent.mkdir(exist_ok=True)
    logfh = open(logpath, "a")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        logfh.write(line + "\n")
        logfh.flush()

    log(f"### run_all escalas={scales} stages={args.stages} reps={args.reps}")
    for sc in scales:
        cmd = [PY, str(ROOT / "bench" / "run_scale.py"), "--scale", str(sc),
               "--stages", args.stages, "--reps", str(args.reps),
               "--batch", str(args.batch)]
        if args.keep_db:
            cmd.append("--keep-db")
        t0 = time.time()
        log(f"-> escala {sc:,}: {' '.join(str(c) for c in cmd[1:])}")
        p = subprocess.run(cmd, capture_output=True, text=True)
        dt = time.time() - t0
        tail = (p.stdout or "").strip().splitlines()[-8:]
        log(f"<- escala {sc:,} rc={p.returncode} en {dt/60:.1f} min")
        for line in tail:
            log("   " + line)
        if p.returncode != 0:
            log("   STDERR: " + (p.stderr or "").strip()[-1500:])
            logfh.write(json.dumps({"scale": sc, "rc": p.returncode}) + "\n")
    log("### run_all terminado")


if __name__ == "__main__":
    main()
