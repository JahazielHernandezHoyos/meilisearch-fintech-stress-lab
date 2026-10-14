"""Fase 2: escribe el dataset a NDJSON en shards de 100k documentos.

Los arreglos generados en gen_arrays.py se leen con mmap (no se duplican en
RAM); cada worker formatea los campos de texto de un rango de ids. La
generacion es determinista: el shard k siempre contiene los ids
[k*100000, (k+1)*100000).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARRAYS = ROOT / "data" / "arrays"
OUT = ROOT / "data" / "ndjson"

VOCALES = set("AEIOU")


def _cons(x: str) -> str:
    for i, ch in enumerate(x.upper()[1:], 1):
        if ch not in VOCALES:
            return ch
    return "X"


CONS_NOMBRE = {n: _cons(n) for n in spec.NOMBRES}
CONS_AP = {a: _cons(a) for a in spec.APELLIDOS}
CONS_MUN = {e[6]: _cons(e[6]) for e in spec.ESTADOS}
ESTADO_CURP = {e[0]: e[2] for e in spec.ESTADOS}
ESTADO_MUN = {e[0]: e[6] for e in spec.ESTADOS}

COLS = ["nombre_idx", "ap_idx", "am_idx", "colonia_idx", "calle_idx", "calle_num",
        "dom_idx", "email_num", "tel", "u0", "u1", "u2", "u3", "estado", "edad",
        "nac_year", "nac_mes", "nac_dia", "score", "ingreso", "monto", "plazo",
        "tasa", "saldo", "limite", "credito_usado", "nums", "atraso",
        "acepta_mkt", "tiene_seguro", "intentos_login", "score_interno",
        "lat", "lng", "cp", "registro_ts", "ultimo_ts",
        "genero", "producto", "kyc_status", "estatus_cuenta", "canal_adquisicion",
        "dispositivo", "banda_riesgo", "banda_ingreso", "tipo_vivienda",
        "nivel_educativo", "tipo_contrato", "segmento_comercial"]


def iso(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


def write_shard(shard: int) -> tuple:
    lo = shard * spec.SHARD_SIZE
    hi = min(lo + spec.SHARD_SIZE, spec.TOTAL)
    if lo >= hi:
        return (shard, 0, 0)
    cols = {c: np.load(ARRAYS / f"{c}.npy", mmap_mode="r")[lo:hi] for c in COLS}
    tagb = np.load(ARRAYS / "_tag_bool.npy", mmap_mode="r")[:, lo:hi]
    NOM, AP, COL, CAL, DOM, TAG = (spec.NOMBRES, spec.APELLIDOS, spec.COLONIAS,
                                   spec.CALLES, spec.DOMINIOS, spec.TAGS)
    catvals = {c[0]: c[1] for c in spec.CATEGORICAS}
    estv = [e[0] for e in spec.ESTADOS]

    path = OUT / f"part-{shard:05d}.jsonl"
    nbytes = 0
    buf = []
    chunk = 4_000
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(hi - lo):
            est = estv[cols["estado"][i]]
            ni = int(cols["nombre_idx"][i]); api = int(cols["ap_idx"][i]); ami = int(cols["am_idx"][i])
            nombre, ap, am = NOM[ni], AP[api], AP[ami]
            col = COL[int(cols["colonia_idx"][i])]
            calle = CAL[int(cols["calle_idx"][i])]
            dom = DOM[int(cols["dom_idx"][i])]
            mun = ESTADO_MUN[est]
            yy = int(cols["nac_year"][i]) % 100
            mm = int(cols["nac_mes"][i]); dd = int(cols["nac_dia"][i])
            gen = catvals["genero"][int(cols["genero"][i])]
            u0, u1, u2, u3 = (int(cols["u0"][i]), int(cols["u1"][i]),
                              int(cols["u2"][i]), int(cols["u3"][i]))
            doc = {
                "id": lo + i + 1,
                "uuid": f"{u0:08x}-{u1 >> 16:04x}-{u1 & 0xffff:04x}-{u2 >> 16:04x}-{u2 & 0xffff:04x}{u3:08x}",
                "nombre": nombre,
                "apellido_paterno": ap,
                "apellido_materno": am,
                "nombre_completo": f"{nombre} {ap} {am}",
                "email": f"{nombre.lower()}.{ap.lower()}{int(cols['email_num'][i]):04d}@{dom}",
                "telefono": f"+52{int(cols['tel'][i])}",
                "curp": (f"{ap[:2]}{nombre[0]}{am[0]}{yy:02d}{mm:02d}{dd:02d}"
                         f"{'H' if gen == 'H' else 'M'}{ESTADO_CURP[est]}"
                         f"{CONS_AP[ap]}{CONS_NOMBRE[nombre]}{CONS_MUN[mun]}{(u0 & 0xFFFF):04X}"),
                "rfc": f"{ap[:2]}{nombre[0]}{am[0]}{yy:02d}{mm:02d}{dd:02d}{(u1 & 0xFFFFFF):06X}",
                "fecha_nacimiento": f"{int(cols['nac_year'][i]):04d}-{mm:02d}-{dd:02d}",
                "edad": int(cols["edad"][i]),
                "genero": gen,
                "estado": est,
                "municipio": mun,
                "colonia": col,
                "cp": int(cols["cp"][i]),
                "direccion": f"{calle} {int(cols['calle_num'][i])}, {col}",
                "_geo": {"lat": round(float(cols["lat"][i]), 6),
                         "lng": round(float(cols["lng"][i]), 6)},
                "producto": catvals["producto"][int(cols["producto"][i])],
                "monto_solicitado": int(cols["monto"][i]),
                "plazo_meses": int(cols["plazo"][i]),
                "tasa_anual": round(float(cols["tasa"][i]), 2),
                "score_buro": int(cols["score"][i]),
                "banda_riesgo": catvals["banda_riesgo"][int(cols["banda_riesgo"][i])],
                "ingreso_mensual": int(cols["ingreso"][i]),
                "banda_ingreso": catvals["banda_ingreso"][int(cols["banda_ingreso"][i])],
                "tipo_contrato": catvals["tipo_contrato"][int(cols["tipo_contrato"][i])],
                "tipo_vivienda": catvals["tipo_vivienda"][int(cols["tipo_vivienda"][i])],
                "nivel_educativo": catvals["nivel_educativo"][int(cols["nivel_educativo"][i])],
                "kyc_status": catvals["kyc_status"][int(cols["kyc_status"][i])],
                "kyc_fecha": f"{2024 + ((lo + i) % 3):04d}-{(1 + (lo + i) % 12):02d}-15",
                "estatus_cuenta": catvals["estatus_cuenta"][int(cols["estatus_cuenta"][i])],
                "num_prestamos": int(cols["nums"][i]),
                "saldo_actual": int(cols["saldo"][i]),
                "dias_atraso": int(cols["atraso"][i]),
                "canal_adquisicion": catvals["canal_adquisicion"][int(cols["canal_adquisicion"][i])],
                "dispositivo": catvals["dispositivo"][int(cols["dispositivo"][i])],
                "segmento_comercial": catvals["segmento_comercial"][int(cols["segmento_comercial"][i])],
                "acepta_marketing": bool(cols["acepta_mkt"][i]),
                "tiene_seguro": bool(cols["tiene_seguro"][i]),
                "intentos_login": int(cols["intentos_login"][i]),
                "score_interno": round(float(cols["score_interno"][i]), 2),
                "limite_credito": int(cols["limite"][i]),
                "credito_usado": int(cols["credito_usado"][i]),
                "utilizacion_pct": round(float(cols["credito_usado"][i]) / max(1, int(cols["limite"][i])) * 100, 2),
                "tags": [TAG[t] for t in range(len(TAG)) if tagb[t, i]],
                "fecha_registro_ts": int(cols["registro_ts"][i]),
                "fecha_registro": iso(cols["registro_ts"][i]),
                "fecha_ultimo_acceso_ts": int(cols["ultimo_ts"][i]),
                "fecha_ultimo_acceso": iso(cols["ultimo_ts"][i]),
            }
            buf.append(json.dumps(doc, separators=(",", ":"), ensure_ascii=True))
            if len(buf) >= chunk:
                s = "\n".join(buf) + "\n"
                fh.write(s); nbytes += len(s); buf.clear()
        if buf:
            s = "\n".join(buf) + "\n"
            fh.write(s); nbytes += len(s)
    return (shard, hi - lo, nbytes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=max(1, os.cpu_count() - 2))
    ap.add_argument("--shards", type=int, default=(spec.TOTAL + spec.SHARD_SIZE - 1) // spec.SHARD_SIZE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if args.procs == 1:
        res = [write_shard(s) for s in range(args.shards)]
    else:
        from multiprocessing import Pool
        with Pool(args.procs) as p:
            res = p.map(write_shard, range(args.shards), chunksize=1)
    total_docs = sum(r[1] for r in res)
    total_bytes = sum(r[2] for r in res)
    dt = time.time() - t0
    print(f"shards={len(res)} docs={total_docs:,} bytes={total_bytes/2**30:.2f} GiB "
          f"t={dt:.1f}s ({total_docs/dt:,.0f} docs/s)", flush=True)


if __name__ == "__main__":
    main()
