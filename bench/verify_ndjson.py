"""Verificacion independiente: recalcula el ground truth leyendo el NDJSON ya
escrito (json.loads por documento, predicados sobre los valores finales del
documento). No usa los arreglos de numpy, asi que detecta cualquier bug de
generacion/escritura. Compara tambien contra gen/ground_truth.json.

  python3 bench/verify_ndjson.py --procs 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gen"))
import spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NDJSON = ROOT / "data" / "ndjson"

PREDS = {
    "seg_estado_cdmx": lambda d: d["estado"] == "Ciudad de Mexico",
    "seg_riesgo_alto_personal": lambda d: d["banda_riesgo"] == "alto" and d["producto"] == "credito_personal",
    "seg_score_bajo": lambda d: d["score_buro"] < 520,
    "seg_morosos_30d": lambda d: d["estatus_cuenta"] == "moroso" and d["dias_atraso"] > 30,
    "seg_kyc_verif_jovenes": lambda d: d["kyc_status"] == "verificado" and 25 <= d["edad"] <= 35,
    "seg_jalisco_ingreso_b": lambda d: d["estado"] == "Jalisco" and d["banda_ingreso"] == "B",
    "seg_tiktok_android_marketing": lambda d: (d["canal_adquisicion"] == "tiktok"
                                               and d["acepta_marketing"] and d["dispositivo"] == "android"),
    "seg_mujeres_30_45_kyc": lambda d: (d["genero"] == "M" and 30 <= d["edad"] <= 45
                                        and d["kyc_status"] == "verificado"),
    "seg_riesgo_muy_alto": lambda d: d["banda_riesgo"] == "muy_alto",
    "seg_activos_sin_atraso": lambda d: d["estatus_cuenta"] == "activo" and d["dias_atraso"] == 0,
    "seg_tag_promo": lambda d: "promo_2026" in d["tags"],
    "seg_nomina_vip_alto_monto": lambda d: (d["producto"] == "credito_nomina"
                                            and d["segmento_comercial"] == "vip"
                                            and d["monto_solicitado"] > 40000),
    "txt_apellido_hernandez": lambda d: (d["apellido_paterno"].startswith("Hernandez")
                                         or d["apellido_materno"].startswith("Hernandez")),
    "txt_apellido_hernandez_riesgo_alto": lambda d: ((d["apellido_paterno"].startswith("Hernandez")
                                                      or d["apellido_materno"].startswith("Hernandez"))
                                                     and d["banda_riesgo"] == "alto"),
    "txt_nombre_maria": lambda d: d["nombre"].startswith("Maria"),
    "txt_nombre_apellido_jalisco": lambda d: (d["nombre"] == "Jose"
                                              and d["apellido_paterno"].startswith("Hernandez")
                                              and d["estado"] == "Jalisco"),
    "txt_colonia_centro": lambda d: d["colonia"].startswith("Centro"),
    "txt_prefix_apellido": lambda d: d["apellido_paterno"].startswith("Hern"),
    "txt_fulltext_default": lambda d: (d["nombre"].startswith("Guadalupe")
                                       or d["apellido_paterno"].startswith("Guadalupe")
                                       or d["apellido_materno"].startswith("Guadalupe")
                                       or d["colonia"].startswith("Guadalupe")),
    "mix_sort_score_riesgo_alto": lambda d: d["banda_riesgo"] == "alto",
    "mix_sort_ingreso_banda_c": lambda d: d["banda_ingreso"] == "C",
    "facet_morosos_producto_riesgo": lambda d: d["estatus_cuenta"] == "moroso",
    "facet_kyc_pendiente_dispositivo": lambda d: d["kyc_status"] == "pendiente",
}

P = 6_371_000.0
import math


def in_geo(d, lat0, lng0, r):
    la = math.radians(d["_geo"]["lat"]); lo = math.radians(d["_geo"]["lng"])
    la0 = math.radians(lat0); lo0 = math.radians(lng0)
    h = math.sin((la - la0) / 2) ** 2 + math.cos(la) * math.cos(la0) * math.sin((lo - lo0) / 2) ** 2
    return P * 2 * math.asin(math.sqrt(h)) <= r


def shard_counts(idx: int):
    p = NDJSON / f"part-{idx:05d}.jsonl"
    if not p.exists():
        return idx, 0, {}
    c = {k: 0 for k in PREDS}
    c["geo_cdmx_25km"] = 0
    c["geo_gdl_50km"] = 0
    c["facet_estado_global"] = 0
    c["facet_score_bajo_canal"] = 0
    n = 0
    with open(p) as fh:
        for line in fh:
            d = json.loads(line)
            n += 1
            for k, fn in PREDS.items():
                if fn(d):
                    c[k] += 1
            if in_geo(d, 19.4326, -99.1332, 25_000):
                c["geo_cdmx_25km"] += 1
            if in_geo(d, 20.6736, -103.3442, 50_000):
                c["geo_gdl_50km"] += 1
            c["facet_estado_global"] += 1
            if d["score_buro"] < 520:
                c["facet_score_bajo_canal"] += 1
    return idx, n, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=10)
    args = ap.parse_args()
    nshards = (spec.TOTAL + spec.SHARD_SIZE - 1) // spec.SHARD_SIZE
    from multiprocessing import Pool
    with Pool(args.procs) as pool:
        res = pool.map(shard_counts, range(nshards), chunksize=1)
    res.sort()
    cum = {}
    per = []
    total = 0
    for idx, n, c in res:
        total += n
        for k, v in c.items():
            cum[k] = cum.get(k, 0) + v
        per.append((total, dict(cum)))
    gt = json.loads((ROOT / "gen" / "ground_truth.json").read_text())
    scales = set(spec.SCALES)
    bad = 0
    checked = 0
    out = {"verificado": [], "discrepancias": []}
    for total_docs, counts in per:
        if total_docs not in scales:
            continue
        for k, v in counts.items():
            exp = gt["scales"][str(total_docs)]["queries"][k]["count"]
            checked += 1
            if v != exp:
                bad += 1
                out["discrepancias"].append({"escala": total_docs, "consulta": k,
                                             "ndjson": v, "ground_truth": exp})
            else:
                out["verificado"].append({"escala": total_docs, "consulta": k, "count": v})
    out["resumen"] = {"comparaciones": checked, "ok": checked - bad, "discrepancias": bad,
                      "docs_totales": total}
    (ROOT / "raw" / "verificacion_ndjson.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out["resumen"], ensure_ascii=False))
    for d in out["discrepancias"][:20]:
        print("DISCREPANCIA", d)


if __name__ == "__main__":
    main()
