"""Fase 1: construye los arreglos deterministas de 4,000,000 de usuarios
ficticios (simulacion fintech) y calcula el GROUND TRUTH exacto de cada consulta por
escala.

El ground truth se computa con numpy sobre los mismos arreglos que alimentan al
NDJSON, jamas consultando a Meilisearch: eso es lo que permite "saber de
antemano" cuantos resultados debe devolver cada segmento.

Salidas:
  data/arrays/*.npy     -> columnas
  data/arrays/_codes.json -> diccionarios codigo->valor
  gen/ground_truth.json -> conteos esperados por consulta y por escala
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARRAYS = ROOT / "data" / "arrays"
ARRAYS.mkdir(parents=True, exist_ok=True)

R = np.random.default_rng(spec.SEED)
N = spec.TOTAL


def choose(values, weights, size):
    w = np.asarray(weights, dtype=np.float64)
    w /= w.sum()
    return R.choice(len(values), size=size, p=w).astype(np.uint8)


def log(msg):
    print(f"[gen {time.strftime('%H:%M:%S')}] {msg}", flush=True)


log(f"generando arreglos para {N:,} registros (seed={spec.SEED})")

# ---------------------------------------------------------------- categorias
codes = {}
cat_arrays = {}
for name, values, weights in spec.CATEGORICAS:
    cat_arrays[name] = choose(values, weights, N)
    codes[name] = values

estado_values = [e[0] for e in spec.ESTADOS]
estado_w = [e[1] for e in spec.ESTADOS]
estado = choose(estado_values, estado_w, N)
codes["estado"] = estado_values

# ---------------------------------------------------------------- nombres
nombre_idx = R.integers(0, len(spec.NOMBRES), N, dtype=np.uint8)
ap_idx = R.integers(0, len(spec.APELLIDOS), N, dtype=np.uint8)
am_idx = R.integers(0, len(spec.APELLIDOS), N, dtype=np.uint8)
colonia_idx = R.integers(0, len(spec.COLONIAS), N, dtype=np.uint8)
calle_idx = R.integers(0, len(spec.CALLES), N, dtype=np.uint8)
calle_num = R.integers(1, 2500, N, dtype=np.uint16)
dom_idx = choose(spec.DOMINIOS, [38, 30, 16, 11, 5], N)
email_num = R.integers(0, 10_000, N, dtype=np.uint32)
tel = R.integers(10**9, 10**10, N, dtype=np.uint64)

# uuid determinista de 128 bits
u = R.integers(0, 2**32, size=(4, N), dtype=np.uint32)

# ---------------------------------------------------------------- edades
edad = (18 + R.gamma(2.2, 7.4, N)).astype(np.int16)
np.clip(edad, 18, 78, out=edad)
edad = edad.astype(np.uint8)

nac_year = 2026 - edad.astype(np.int32)
nac_mes = R.integers(1, 13, N, dtype=np.uint8)
nac_dia = R.integers(1, 29, N, dtype=np.uint8)

# ---------------------------------------------------------------- score buro
riesgo_code = cat_arrays["banda_riesgo"]
score = np.empty(N, dtype=np.int16)
for i, (bname, (mu, sd)) in enumerate(spec.SCORE_POR_RIESGO.items()):
    m = riesgo_code == i
    score[m] = np.round(R.normal(mu, sd, int(m.sum()))).astype(np.int16)
np.clip(score, 300, 850, out=score)
score = score.astype(np.uint16)

# ---------------------------------------------------------------- ingresos
ing_code = cat_arrays["banda_ingreso"]
ingreso = np.empty(N, dtype=np.int32)
for i, (bname, (mu, sd)) in enumerate(spec.INGRESO_POR_BANDA.items()):
    m = ing_code == i
    ingreso[m] = np.round(R.normal(mu, sd, int(m.sum()))).astype(np.int32)
np.clip(ingreso, 2_400, 400_000, out=ingreso)

# ---------------------------------------------------------------- credito
monto = np.round(np.exp(R.normal(9.1, 0.85, N))).astype(np.int32)
np.clip(monto, 500, 80_000, out=monto)
plazo = R.choice([4, 6, 8, 12, 18, 24], size=N, p=[.22, .26, .2, .17, .09, .06]).astype(np.uint8)
tasa = (18.0 + R.gamma(2.0, 6.5, N) + riesgo_code * 3.5).round(2)
saldo = np.round(monto * R.uniform(0, 1, N) * (1 + riesgo_code * 0.15)).astype(np.int32)
limite = np.round(ingreso * R.uniform(0.5, 2.5, N)).astype(np.int32)
credito_usado = np.round(limite * R.uniform(0, 1.05, N)).astype(np.int32)
np.clip(credito_usado, 0, limite, out=credito_usado)

nums = R.poisson(3.2, N).astype(np.uint8)
np.clip(nums, 0, 30, out=nums)

# dias de atraso: 72% en cero, resto cola larga
atraso = np.zeros(N, dtype=np.uint16)
no_cero = R.random(N) < 0.28
atraso[no_cero] = np.round(np.exp(R.normal(3.4, 1.15, int(no_cero.sum())))).astype(np.uint16)
np.clip(atraso, 0, 400, out=atraso)

# ---------------------------------------------------------------- flags
acepta_mkt = (R.random(N) < 0.63)
tiene_seguro = (R.random(N) < 0.35)
intentos_login = np.clip(R.poisson(6.5, N), 1, 90).astype(np.uint8)
score_interno = np.round(R.uniform(0, 1000, N), 2)

# ---------------------------------------------------------------- geo + cp
est_lat = np.array([e[3] for e in spec.ESTADOS], dtype=np.float32)
est_lng = np.array([e[4] for e in spec.ESTADOS], dtype=np.float32)
est_cp = np.array([e[5] for e in spec.ESTADOS], dtype=np.int32)
lat = (est_lat[estado] + R.normal(0, 0.22, N)).astype(np.float32)
lng = (est_lng[estado] + R.normal(0, 0.22, N)).astype(np.float32)
cp = est_cp[estado] + R.integers(0, 1000, N).astype(np.int32)

# ---------------------------------------------------------------- tiempos
T0 = 1_672_531_200   # 2023-01-01
T1 = 1_759_000_000   # ~2025-09 (antes de "hoy")
registro_ts = R.integers(T0, T1, N, dtype=np.int64)
ultimo_ts = registro_ts + (R.exponential(9_000_000, N)).astype(np.int64)
np.clip(ultimo_ts, registro_ts, 1_788_000_000, out=ultimo_ts)  # cap ~2026-08

# ---------------------------------------------------------------- tags
tag_bool = np.zeros((len(spec.TAGS), N), dtype=bool)
tag_p = [.18, .09, .07, .12, .10, .15, .15, .05, .03, .22, .11, .31]
for i, p in enumerate(tag_p):
    tag_bool[i] = R.random(N) < p
# correlaciones realistas
tag_bool[0] &= acepta_mkt                                    # promo_2026
tag_bool[7] |= (ingreso > 35_000) & (R.random(N) < 0.5)      # alto_valor
tag_bool[4] |= atraso > 30                                    # cobranza
tag_bool[9] |= (cat_arrays["kyc_status"] == 0) & (R.random(N) < 0.75)
tag_bool[1] = tag_bool[1] | (cat_arrays["segmento_comercial"] == 2)

# ---------------------------------------------------------------- guardado
out = {
    "nombre_idx": nombre_idx, "ap_idx": ap_idx, "am_idx": am_idx,
    "colonia_idx": colonia_idx, "calle_idx": calle_idx, "calle_num": calle_num,
    "dom_idx": dom_idx, "email_num": email_num, "tel": tel,
    "u0": u[0], "u1": u[1], "u2": u[2], "u3": u[3],
    "estado": estado, "edad": edad, "nac_year": nac_year.astype(np.uint16),
    "nac_mes": nac_mes, "nac_dia": nac_dia,
    "score": score, "ingreso": ingreso, "monto": monto, "plazo": plazo,
    "tasa": tasa.astype(np.float32), "saldo": saldo, "limite": limite,
    "credito_usado": credito_usado, "nums": nums, "atraso": atraso,
    "acepta_mkt": acepta_mkt, "tiene_seguro": tiene_seguro,
    "intentos_login": intentos_login, "score_interno": score_interno,
    "lat": lat, "lng": lng, "cp": cp,
    "registro_ts": registro_ts.astype(np.int64), "ultimo_ts": ultimo_ts,
}
out.update(cat_arrays)

for k, v in out.items():
    np.save(ARRAYS / f"{k}.npy", v)
np.save(ARRAYS / "_tag_bool.npy", tag_bool)

codes.update({
    "estado": estado_values,
    "dom": spec.DOMINIOS,
    "nombre": spec.NOMBRES,
    "apellido": spec.APELLIDOS,
    "colonia": spec.COLONIAS,
    "calle": spec.CALLES,
    "tags": spec.TAGS,
    "nac_mes": None, "nac_dia": None, "dom_idx": spec.DOMINIOS,
})
(ARRAYS / "_codes.json").write_text(json.dumps(codes, ensure_ascii=False))
log(f"arreglos guardados en {ARRAYS} ({len(out)+1} columnas)")

# ================================================================ GROUND TRUTH
log("calculando ground truth ...")
A = out

bearings = dict(zip(estado_values, range(len(estado_values))))


def eq(field, value):
    return A[field] == codes[field].index(value)


def mask_estado(name):
    return A["estado"] == bearings[name]


def tags_has(tag):
    return tag_bool[spec.TAGS.index(tag)]


def haversine_mask(lat0, lng0, radius_m):
    la = np.radians(A["lat"].astype(np.float64))
    lo = np.radians(A["lng"].astype(np.float64))
    la0 = np.radians(lat0)
    lo0 = np.radians(lng0)
    dla = la - la0
    dlo = lo - lo0
    h = np.sin(dla / 2) ** 2 + np.cos(la) * np.cos(la0) * np.sin(dlo / 2) ** 2
    return 6_371_000.0 * 2 * np.arcsin(np.sqrt(h)) <= radius_m


# --- mascaras base (sobre el dataset completo) ---
M = {}
M["seg_estado_cdmx"] = mask_estado("Ciudad de Mexico")
M["seg_riesgo_alto_personal"] = (eq("banda_riesgo", "alto") & eq("producto", "credito_personal"))
M["seg_score_bajo"] = A["score"] < 520
M["seg_morosos_30d"] = eq("estatus_cuenta", "moroso") & (A["atraso"] > 30)
M["seg_kyc_verif_jovenes"] = eq("kyc_status", "verificado") & (A["edad"] >= 25) & (A["edad"] <= 35)
M["seg_jalisco_ingreso_b"] = mask_estado("Jalisco") & eq("banda_ingreso", "B")
M["seg_tiktok_android_marketing"] = (eq("canal_adquisicion", "tiktok") & A["acepta_mkt"]
                                     & eq("dispositivo", "android"))
M["seg_mujeres_30_45_kyc"] = (eq("genero", "M") & (A["edad"] >= 30) & (A["edad"] <= 45)
                              & eq("kyc_status", "verificado"))
M["seg_riesgo_muy_alto"] = eq("banda_riesgo", "muy_alto")
M["seg_activos_sin_atraso"] = eq("estatus_cuenta", "activo") & (A["atraso"] == 0)
M["seg_tag_promo"] = tags_has("promo_2026")
M["seg_nomina_vip_alto_monto"] = (eq("producto", "credito_nomina")
                                  & eq("segmento_comercial", "vip") & (A["monto"] > 40000))
M["geo_cdmx_25km"] = haversine_mask(19.4326, -99.1332, 25_000)
M["geo_gdl_50km"] = haversine_mask(20.6736, -103.3442, 50_000)
def _pref_table(strings, prefix):
    """Meilisearch aplica prefix search sobre la ULTIMA palabra de la consulta:
    un token del documento coincide si empieza por ese prefijo (minusculas)."""
    p = prefix.lower()
    return np.array([s.lower().startswith(p) for s in strings])


HERN = _pref_table(spec.APELLIDOS, "Hernandez")
MARIA = _pref_table(spec.NOMBRES, "Maria")
HERN_PREF = _pref_table(spec.APELLIDOS, "Hern")
CENTRO = _pref_table(spec.COLONIAS, "Centro")
GUAD_N = _pref_table(spec.NOMBRES, "Guadalupe")
GUAD_A = _pref_table(spec.APELLIDOS, "Guadalupe")
GUAD_C = _pref_table(spec.COLONIAS, "Guadalupe")

M["txt_apellido_hernandez"] = HERN[A["ap_idx"]] | HERN[A["am_idx"]]
M["txt_nombre_maria"] = MARIA[A["nombre_idx"]]
M["txt_nombre_apellido_jalisco"] = ((A["nombre_idx"] == spec.NOMBRES.index("Jose"))
                                    & HERN[A["ap_idx"]]
                                    & mask_estado("Jalisco"))
M["txt_apellido_hernandez_riesgo_alto"] = (M["txt_apellido_hernandez"] & eq("banda_riesgo", "alto"))
M["txt_prefix_apellido"] = HERN_PREF[A["ap_idx"]]
M["txt_colonia_centro"] = CENTRO[A["colonia_idx"]]
# sonda fulltext sobre todos los campos buscables (token "guadalupe" como prefijo)
M["txt_fulltext_default"] = (GUAD_N[A["nombre_idx"]] | GUAD_A[A["ap_idx"]]
                             | GUAD_A[A["am_idx"]] | GUAD_C[A["colonia_idx"]])
M["mix_sort_score_riesgo_alto"] = eq("banda_riesgo", "alto")
M["mix_sort_ingreso_banda_c"] = eq("banda_ingreso", "C")
M["facet_estado_global"] = np.ones(N, dtype=bool)
M["facet_morosos_producto_riesgo"] = eq("estatus_cuenta", "moroso")
M["facet_score_bajo_canal"] = A["score"] < 520
M["facet_kyc_pendiente_dispositivo"] = eq("kyc_status", "pendiente")
M["deep_activos_sin_atraso"] = M["seg_activos_sin_atraso"]
M["deep_score_bajo"] = M["seg_score_bajo"]
M["deep_sin_filtro"] = np.ones(N, dtype=bool)

FACETS = {
    "facet_estado_global": ["estado"],
    "facet_morosos_producto_riesgo": ["producto", "banda_riesgo"],
    "facet_score_bajo_canal": ["canal_adquisicion"],
    "facet_kyc_pendiente_dispositivo": ["dispositivo", "acepta_marketing"],
}

PROFILE_FIELDS = ["estado", "producto", "kyc_status", "estatus_cuenta",
                  "canal_adquisicion", "dispositivo", "banda_riesgo",
                  "banda_ingreso", "genero", "segmento_comercial",
                  "nivel_educativo", "tipo_contrato"]

gt = {"meta": {"seed": spec.SEED, "total": N,
               "generado": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "meilisearch_version": "1.55.0"}, "scales": {}}

for scale in spec.SCALES:
    per = {}
    for q in spec.QUERIES:
        m = M[q["id"]][:scale]
        entry = {"count": int(m.sum())}
        if q["id"] in FACETS:
            f = {}
            for field in FACETS[q["id"]]:
                if field == "acepta_marketing":
                    vals, cnts = np.unique(A["acepta_mkt"][:scale][m], return_counts=True)
                    f[field] = {str(bool(v)).lower(): int(c) for v, c in zip(vals, cnts)}
                else:
                    col = A[field][:scale][m]
                    cnts = np.bincount(col, minlength=len(codes[field]))
                    f[field] = {codes[field][i]: int(c) for i, c in enumerate(cnts) if c}
            entry["facets"] = f
        if q["tipo"] in ("filter", "geo", "sort"):
            idx = np.flatnonzero(m)[:5]
            entry["sample_ids"] = [int(i) + 1 for i in idx]
        per[q["id"]] = entry
    for dp in spec.DEEP_PAGINATION:
        per[dp["id"]] = {"count": int(M[dp["id"]][:scale].sum())}
    prof = {}
    for field in PROFILE_FIELDS:
        col = A[field][:scale]
        cnts = np.bincount(col, minlength=len(codes[field]))
        prof[field] = {codes[field][i]: int(c) for i, c in enumerate(cnts) if c}
    gt["scales"][str(scale)] = {"docs": scale, "queries": per, "profile": prof, "bytes_ndjson_aprox": None}
    log(f"  escala {scale:,}: " + ", ".join(f"{k}={v}" for k, v in
        [(q, per[q]["count"]) for q in ("seg_score_bajo", "seg_activos_sin_atraso", "geo_cdmx_25km")]))

(ROOT / "gen" / "ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False))
log("ground truth escrito en gen/ground_truth.json")
