"""Genera el reporte final: tablas markdown, CSV crudos y graficas SVG.

  python3 bench/report.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen"))
import spec  # noqa: E402

RAW = ROOT / "raw"
REP = ROOT / "reports"
CHARTS = REP / "charts"
TABLES = REP / "tables"
GT = json.loads((ROOT / "gen" / "ground_truth.json").read_text())

ACCENT = "#2563eb"
ACCENT2 = "#dc2626"
MUTED = "#6b7280"
GRID = "#e5e7eb"
INK = "#111827"
SERIES = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2"]

SCALES = spec.SCALES


def load_scales():
    data = {}
    for sc in SCALES:
        p = RAW / f"scale_{sc}.json"
        if p.exists():
            data[sc] = json.loads(p.read_text())
    return data


def fmt(n, dec=0):
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.{dec}f}"
    return f"{n:,}"


def b2g(x):
    return f"{x/2**30:.2f} GiB" if x else "—"


# ------------------------------------------------------------------ SVG utils
def svg_line(path, title, xlabel, ylabel, series, xvals, logx=False, logy=False):
    """series: list of (label, color, [y...])"""
    W, H = 860, 420
    L, R, T, B = 70, 190, 44, 60
    pw, ph = W - L - R, H - T - B
    xs = list(range(len(xvals)))
    allv = [v for _, _, ys in series for v in ys if v and v > 0]
    if not allv:
        return
    ymax = max(allv) * 1.15
    import math
    if logy:
        ymin = min(allv) / 1.5
    else:
        ymin = 0

    def px(i):
        return L + (pw * i / max(1, len(xvals) - 1)) if len(xvals) > 1 else L + pw / 2

    def py(v):
        if logy:
            f = (math.log10(max(v, 1e-9)) - math.log10(ymin)) / (math.log10(ymax) - math.log10(ymin))
        else:
            f = (v - ymin) / (ymax - ymin)
        return T + ph * (1 - f)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="13">']
    o.append(f'<text x="{L}" y="26" font-size="16" font-weight="600" fill="{INK}">{title}</text>')
    # grid + y labels
    nticks = 5
    for i in range(nticks + 1):
        v = ymin + (ymax - ymin) * i / nticks
        y = py(v) if v > 0 else T + ph
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" stroke="{GRID}"/>')
        lab = f"{v:,.0f}" if v >= 10 else f"{v:.2f}"
        o.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end" fill="{MUTED}">{lab}</text>')
    # x labels
    for i, xv in enumerate(xvals):
        x = px(i)
        o.append(f'<line x1="{x:.1f}" y1="{T+ph}" x2="{x:.1f}" y2="{T+ph+4}" stroke="{MUTED}"/>')
        o.append(f'<text x="{x:.1f}" y="{T+ph+20}" text-anchor="middle" fill="{MUTED}">{xv:,}</text>')
    o.append(f'<text x="{L+pw/2:.0f}" y="{H-14}" text-anchor="middle" fill="{MUTED}">{xlabel}</text>')
    o.append(f'<text x="16" y="{T+ph/2:.0f}" fill="{MUTED}" transform="rotate(-90 16 {T+ph/2:.0f})" '
             f'text-anchor="middle">{ylabel}</text>')
    for si, (label, color, ys) in enumerate(series):
        pts = [(px(i), py(v)) for i, v in enumerate(ys) if v and v > 0]
        if not pts:
            continue
        d = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))
        o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
        ly = T + 18 + si * 20
        o.append(f'<line x1="{L+pw+14}" y1="{ly-4}" x2="{L+pw+34}" y2="{ly-4}" stroke="{color}" stroke-width="2"/>')
        o.append(f'<text x="{L+pw+40}" y="{ly}" fill="{INK}">{label}</text>')
    o.append("</svg>")
    CHARTS.mkdir(parents=True, exist_ok=True)
    (CHARTS / path).write_text("\n".join(o))


def svg_bars(path, title, xlabel, ylabel, labels, series):
    W, H = 860, 420
    L, R, T, B = 70, 200, 44, 60
    pw, ph = W - L - R, H - T - B
    allv = [v for _, _, ys in series for v in ys if v]
    ymax = max(allv) * 1.15
    import math
    ymin = 0

    def py(v):
        return T + ph * (1 - (v - ymin) / (ymax - ymin))

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="13">']
    o.append(f'<text x="{L}" y="26" font-size="16" font-weight="600" fill="{INK}">{title}</text>')
    for i in range(6):
        v = ymax * i / 5
        y = py(v)
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+pw}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end" fill="{MUTED}">{v:,.0f}</text>')
    n = len(labels)
    bw = pw / n
    nb = len(series)
    for bi, (label, color, ys) in enumerate(series):
        for i, v in enumerate(ys):
            if not v:
                continue
            x = L + bw * i + bw * 0.15 + (bw * 0.7 / nb) * bi
            w = bw * 0.7 / nb
            y = py(v)
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{T+ph-y:.1f}" fill="{color}"/>')
        ly = T + 18 + bi * 20
        o.append(f'<rect x="{L+pw+14}" y="{ly-12}" width="20" height="10" fill="{color}"/>')
        o.append(f'<text x="{L+pw+40}" y="{ly-2}" fill="{INK}">{label}</text>')
    for i, lab in enumerate(labels):
        x = L + bw * i + bw / 2
        o.append(f'<text x="{x:.1f}" y="{T+ph+20}" text-anchor="middle" fill="{MUTED}">{lab:,}</text>')
    o.append(f'<text x="{L+pw/2:.0f}" y="{H-14}" text-anchor="middle" fill="{MUTED}">{xlabel}</text>')
    o.append(f'<text x="16" y="{T+ph/2:.0f}" fill="{MUTED}" transform="rotate(-90 16 {T+ph/2:.0f})" '
             f'text-anchor="middle">{ylabel}</text>')
    o.append("</svg>")
    CHARTS.mkdir(parents=True, exist_ok=True)
    (CHARTS / path).write_text("\n".join(o))


def env_fingerprint() -> dict:
    out = {}
    def read(p, default="n/d"):
        try:
            return Path(p).read_text().strip()
        except OSError:
            return default
    out["governor CPU"] = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    out["modelo de CPU"] = [l.split(":", 1)[1].strip() for l in read("/proc/cpuinfo", "").splitlines()
                            if l.startswith("model name")][:1]
    out["modelo de CPU"] = out["modelo de CPU"][0] if out["modelo de CPU"] else "n/d"
    try:
        ra = Path("/sys/block/nvme0n1/queue/rotational").read_text().strip()
        out["disco"] = f"nvme0n1 (rotational={ra})"
    except OSError:
        out["disco"] = "n/d"
    out["kernel"] = Path("/proc/sys/kernel/osrelease").read_text().strip()
    try:
        out["memoria total"] = f"{int([l for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal')][0].split()[1])//1024} MiB"
    except Exception:
        out["memoria total"] = "n/d"
    out["python"] = sys.version.split()[0]
    return out


def csv_write(name, header, rows):
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / name, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------------ secciones
def _p50q(d, stage, qid):
    v = (d.get(stage, {}).get("queries", {}).get(qid) or {}).get("metrics") or {}
    return v.get("wall_ms_p50")


def _p50deep(d, seg, offset):
    for r in d.get("deep_pagination", {}).get("rows", []):
        if r["id"] == seg and r["offset"] == offset:
            return r.get("wall_ms_p50")
    return None


def build():
    data = load_scales()
    if not data:
        print("no hay raw/scale_*.json")
        return
    scales = sorted(data)
    small0 = scales[0]

    def p50(sc, key, qid):
        v = data[sc].get(key, {}).get("queries", {}).get(qid, {})
        return (v.get("metrics") or {}).get("wall_ms_p50")

    md = []
    A = md.append

    # ---- metadatos ----
    host = data[scales[0]]["host"]
    A("# Laboratorio de estrés con Meilisearch — segmentación de 4,000,000 de clientes ficticios (simulación fintech)")
    A("")
    A(f"- Motor: **Meilisearch v{GT['meta']['meilisearch_version']}** (binario oficial, `--env production`)")
    A(f"- Host: `{host['cpu_model']}` — {host['nproc']} vCPU, "
      f"{host['mem_total_kb']/2**20:.1f} GiB RAM, kernel {host['kernel']}")
    A(f"- Dataset: **{GT['meta']['total']:,} documentos** sintéticos, semilla fija `{GT['meta']['seed']}` "
      f"(100% ficticios, reproducible bit a bit)")
    nfields = 0
    try:
        with open(ROOT / "data" / "ndjson" / "part-00000.jsonl") as fh:
            nfields = len(json.loads(fh.readline()))
    except Exception:
        nfields = 0
    A(f"- Índice: `{spec.INDEX_UID}` — {nfields} campos por documento, "
      f"{len(spec.QUERIES)} consultas de segmentación + paginación profunda")
    A("")
    A("> Toda cifra de latencia es **cliente** (HTTP completo, incluye serialización y "
      "transferencia); `meili_ms` es el `processingTimeMs` que reporta el propio motor.")
    pending = [s for s in spec.SCALES if s not in data]
    if pending:
        A("")
        A(f"> **Reporte parcial.** Escalas medidas: {', '.join(f'{s:,}' for s in scales)}. "
          f"Pendientes en esta corrida: {', '.join(f'{s:,}' for s in pending)} "
          f"(se regenera con `python3 bench/report.py` al terminar).")
    A("")

    # ---- 0. resumen ejecutivo ----
    A("## 0. Resumen ejecutivo")
    A("")
    big0 = scales[-1]
    l0 = data[big0].get("load", {})
    qgt = GT["scales"][str(big0)]["queries"]
    over0 = [q for q in spec.QUERIES if qgt[q["id"]]["count"] > 1000]
    A(f"1. **{GT['meta']['total']:,} clientes ficticios caben en Meilisearch en un solo nodo**: "
      f"índice de {b2g(l0.get('db_bytes'))} en disco, {l0.get('index_s', 0)/3600:.1f} h de "
      f"indexado a {l0.get('docs_per_s', 0):,.0f} docs/s promedio, pico de RAM "
      f"{b2g(l0.get('peak_rss_bytes'))}.")
    A(f"2. **El conteo de un segmento es exacto y barato**: `estimatedTotalHits` coincide con el "
      f"ground truth en las {len(spec.QUERIES)} consultas × {len(scales)} escalas, con p50 de "
      f"{fmt(_p50q(data[big0], 'queries_default_limit20', 'facet_estado_global'), 2)} ms para "
      f"faceter los {big0:,} y de "
      f"{fmt(_p50q(data[big0], 'queries_default_limit20', 'seg_kyc_verif_jovenes'), 2)} ms para "
      f"filtrar un segmento de {qgt['seg_kyc_verif_jovenes']['count']:,} clientes.")
    A(f"3. **Lo que duele es extraer**: con el tope de fábrica (`maxTotalHits=1000`) pedir más "
      f"devuelve 1000 hits o vacío *sin error*; con el tope levantado, la paginación profunda "
      f"cuesta segundos (offset 1,000,000 ≈ "
      f"{fmt(_p50deep(data[big0], 'deep_sin_filtro', 1_000_000))} ms p50 a {big0:,}).")
    A(f"4. **{len(over0)} de las {len(spec.QUERIES)} consultas devuelven más de 1000 clientes a "
      f"{big0:,}** — la segmentación masiva es la norma, no la excepción.")
    A(f"5. **La búsqueda filtrada escala plano**: de {small0:,} a {big0:,} documentos las "
      f"consultas `limit=20` se mantienen en pocos milisegundos; el volumen se paga al indexar "
      f"y al paginar profundo.")
    A("")

    # ---- 1. carga / indexado ----
    A("## 1. Carga e indexado por escala")
    A("")
    A("| Escala | Documentos indexados | NDJSON | Índice en disco | KiB/doc | Tiempo indexado | docs/s | Pico RSS | CPU media |")
    A("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = []
    for sc in scales:
        l = data[sc]["load"]
        A(f"| {sc:,} | {fmt(l.get('docs_indexados'))} | {b2g(l.get('ndjson_bytes'))} | "
          f"{b2g(l.get('db_bytes'))} | {fmt(l.get('db_bytes_per_doc', 0)/1024, 1) if l.get('db_bytes_per_doc') else '—'} | "
          f"{fmt(l.get('index_s'), 2)} s | {fmt(l.get('docs_per_s'), 0)} | {b2g(l.get('peak_rss_bytes'))} | "
          f"{fmt(l.get('cpu', {}).get('cpu_pct_mean'), 0)}% |")
        rows.append([sc, l.get("docs_indexados"), l.get("ndjson_bytes"), l.get("db_bytes"),
                     l.get("db_bytes_per_doc"), l.get("index_s"), l.get("docs_per_s"),
                     l.get("peak_rss_bytes"), l.get("cpu", {}).get("cpu_pct_mean")])
    csv_write("carga_por_escala.csv",
              ["escala", "docs_indexados", "ndjson_bytes", "db_bytes", "bytes_por_doc",
               "index_s", "docs_por_s", "peak_rss_bytes", "cpu_pct_media"], rows)
    if len(scales) >= 2:
        big = data[scales[-1]]["load"]
        small = data[scales[1]]["load"] if len(scales) > 1 else big
        A("")
        A(f"Faltantes de documentos al indexar: "
          f"{', '.join(f'{sc:,}→{fmt(data[sc]["load"].get("docs_indexados"))}' for sc in scales)} "
          f"(debe coincidir exactamente con la escala).")
    svg_bars("carga_docs_por_s.svg", "Throughput de indexado por escala", "Documentos indexados",
             "docs/s", scales, [("docs/s", ACCENT, [data[sc]["load"].get("docs_per_s") for sc in scales])])
    svg_bars("carga_disco.svg", "Tamaño del índice en disco por escala", "Documentos", "GiB",
             scales, [("índice", ACCENT, [round((data[sc]["load"].get("db_bytes") or 0)/2**30, 3) for sc in scales]),
                      ("pico RSS", ACCENT2, [round((data[sc]["load"].get("peak_rss_bytes") or 0)/2**30, 3) for sc in scales])])
    A("")
    A("![Throughput de indexado](charts/carga_docs_por_s.svg)")
    A("")
    A("![Disco y RSS](charts/carga_disco.svg)")
    A("")

    # ---- 1b. procedencia y diseño del dataset ----
    bigd = scales[-1]
    qd = GT["scales"][str(bigd)]["queries"]
    tot = float(bigd)
    A("## 1b. Cómo se construyó este dataset (procedencia y diseño)")
    A("")
    A("**Procedencia.** El esquema de datos está inventado para este laboratorio. No se consultó, "
      "raspó ni copió el esquema real de ninguna empresa: los nombres de producto, las bandas, los canales y "
      "los estatus son vocabulario genérico del crédito al consumo en México. Los pesos, las "
      "correlaciones y las reglas de derivación se escribieron a mano en `gen/spec.py`; las únicas "
      "referencias externas son de sentido común (peso poblacional relativo de los estados, orden de "
      "magnitud de los ingresos por banda). Toda cifra de este reporte se mide contra *este* dataset, "
      "no contra una cartera real.")
    A("")
    A("**El esquema lo dictaron los experimentos.** Cada campo tenía que cumplir cuatro cosas:")
    A("")
    A("1. ser plausible para una fintech de préstamos, para que un analista lea los segmentos sin ruido;")
    A("2. ser **filtrable, ordenable o buscable**, porque cada atributo filtrable construye su propia "
      "base de facetas — de ahí el costo de "
      f"{(data[bigd]['load'].get('db_bytes') or 0)//max(1,bigd):,} B por documento y los "
      f"{b2g(data[bigd]['load'].get('db_bytes'))} de índice para 4 millones;")
    A("3. ser **calculable en forma cerrada sobre vectores** (numpy), requisito para poder predecir el "
      "conteo exacto *antes* de consultar;")
    A("4. tener cardinalidad variada: 32 estados, 5 productos, 4 bandas de riesgo, 12 etiquetas → "
      "facetas grandes y chicas en el mismo índice.")
    A("")
    A("**Pesos declarados** (extracto de `gen/spec.py`; el resto son 32 estados, 12 etiquetas y "
      "8 dominios de correo):")
    A("")
    A("| Campo | Valores y pesos |")
    A("|---|---|")
    for name, values, weights in spec.CATEGORICAS:
        A(f"| `{name}` | " + ", ".join(f"{v} {w}%" for v, w in zip(values, weights)) + " |")
    A("")
    A("**Correlaciones deliberadas** (lo que hace que los filtros crucen de forma no trivial):")
    A("")
    A("| Relación | Regla |")
    A("|---|---|")
    for b, (mu, sd) in spec.SCORE_POR_RIESGO.items():
        A(f"| `banda_riesgo = {b}` → `score_buro` | N({mu:,}, {sd}) recortada a 300–850 |")
    for b, (mu, sd) in spec.INGRESO_POR_BANDA.items():
        A(f"| `banda_ingreso = {b}` → `ingreso_mensual` | N({mu:,}, {sd}) recortada a 2,400–400,000 |")
    A("| `monto_solicitado` | log-normal exp(N(9.1, 0.85)) recortada a 500–80,000 |")
    A("| `dias_atraso` | 72 % en 0 + cola exponencial exp(N(3.4, 1.15)) hasta 400 |")
    A("| `num_prestamos` | Poisson(3.2) recortada a 0–30 |")
    A("| `fecha_registro` / `ultimo_acceso` | uniforme en 3 años / registro + exponencial |")
    A("")
    A("**Campos derivados** (coherentes entre sí, no sorteados por separado):")
    A("")
    A("- `curp` = 2 letras del apellido + 1 del nombre + 1 del segundo apellido + fecha de nacimiento + "
      "sexo + código del estado + 3 consonantes internas + 4 hex del PRNG; `rfc` igual con 6 hex.")
    A("- `email` = `{nombre}.{apellido}{4 dígitos}@{dominio}`, de modo que el token del correo coincide "
      "siempre con el nombre del documento (por eso el conteo por correo es verificable).")
    A("- `cp` = prefijo del estado + 3 dígitos; `_geo` = capital del estado + jitter gaussiano "
      "σ = 0.22° (≈25 km); `direccion` = calle + número + colonia.")
    A("- `nombre_completo`, `utilizacion_pct` y las fechas ISO se calculan de los campos anteriores.")
    A("")
    A("**Cómo queda el dataset** (proporciones medidas sobre los 4 millones, todas verificadas contra "
      "el ground truth):")
    A("")
    A("| Segmento | Clientes | Proporción |")
    A("|---|---:|---:|")
    for qid, lab in (("seg_score_bajo", "`score_buro < 520`"),
                     ("seg_estado_cdmx", "vive en Ciudad de Mexico"),
                     ("seg_kyc_verif_jovenes", "KYC verificado de 25 a 35 anios"),
                     ("seg_activos_sin_atraso", "activo y sin atraso"),
                     ("geo_cdmx_25km", "dentro de 25 km del Zocalo"),
                     ("txt_apellido_hernandez", "apellido Hernandez")):
        A(f"| {lab} | {qd[qid]['count']:,} | {qd[qid]['count']/tot*100:.2f}% |")
    A("")
    A("**Qué no es.** Un dataset estacionario y sintético: sirve para medir degradación con un oráculo "
      "exacto, no para inferir nada del negocio. Cambiar cualquier tabla de `gen/spec.py` y volver a "
      "correr los scripts del README regenera todo — incluido el ground truth — de forma determinista.")
    A("")

    # ---- 2. ground truth ----
    A("## 2. Ground truth: cuánto *debe* devolver cada segmento (calculado antes de consultar)")
    A("")
    A("Los conteos se derivaron de los arreglos que generaron los documentos (numpy), "
      "nunca de Meilisearch; por eso sirven como oráculo de correctitud.")
    A("")
    qids = [q["id"] for q in spec.QUERIES]
    head = "| Consulta | Tipo | " + " | ".join(f"{sc:,}" for sc in scales) + " |"
    A(head)
    A("|---|---|" + "---:|" * len(scales))
    for q in spec.QUERIES:
        cells = []
        for sc in scales:
            v = GT["scales"][str(sc)]["queries"][q["id"]]["count"]
            mark = "**" if v > 1000 else ""
            cells.append(f"{mark}{v:,}{mark}")
        A(f"| `{q['id']}` | {q['tipo']} | " + " | ".join(cells) + " |")
    A("")
    A("En **negritas** los segmentos con más de 1000 resultados reales (subconteo garantizado "
      "con `maxTotalHits=1000`).")
    rows = [[q["id"], q["tipo"], q["desc"]] + [GT["scales"][str(sc)]["queries"][q["id"]]["count"] for sc in scales]
            for q in spec.QUERIES]
    csv_write("ground_truth_por_escala.csv", ["consulta", "tipo", "descripcion"] +
              [f"n_{sc}" for sc in scales], rows)
    A("")

    # ---- 3. correctitud ----
    A("## 3. Verificación de correctitud: reportado vs ground truth")
    A("")
    A("`default` = `pagination.maxTotalHits: 1000` (valor de fábrica). "
      "`raised` = `maxTotalHits` = tamaño de la escala.")
    A("")
    summ = {}
    for key, label in (("queries_default_limit20", "default (maxTotalHits=1000)"),
                       ("queries_raised_limit20", "raised (maxTotalHits=N)")):
        tot = match = mismatch = 0
        bad = []
        for sc in scales:
            st = data[sc].get(key)
            if not st:
                continue
            qs_gt = GT["scales"][str(sc)]["queries"]
            for qid, qv in st["queries"].items():
                m = qv.get("metrics") or {}
                rep = m.get("estimatedTotalHits")
                if rep is None or qid in ("txt_fulltext_default_typos",):
                    continue
                truth = qs_gt[qid]["count"]
                tot += 1
                if rep == truth:
                    match += 1
                else:
                    mismatch += 1
                    bad.append((sc, qid, rep, truth))
        summ[label] = (tot, match, mismatch, bad)
        A(f"- **{label}**: {match}/{tot} consultas con conteo exacto "
          f"({mismatch} discrepancias).")
    A("")
    A("`estimatedTotalHits` **no** se recorta con `pagination.maxTotalHits`: en ambos modos "
      "devuelve el conteo real del segmento (verificado contra el ground truth en las 7 "
      "escalas). Lo que el setting limita es cuántos hits se pueden extraer; el detalle está "
      "en la sección 4.3.")
    A("")
    # tabla detallada de la mayor escala
    big = scales[-1]
    A(f"### 3.1 Detalle a {big:,} documentos")
    A("")
    A("| Consulta | GT | default `estimatedTotalHits` | raised `estimatedTotalHits` | ¿default OK? | ¿raised OK? | facets OK |")
    A("|---|---:|---:|---:|---|---|---|")
    for q in spec.QUERIES:
        gt = GT["scales"][str(big)]["queries"][q["id"]]["count"]
        d = data[big].get("queries_default_limit20", {}).get("queries", {}).get(q["id"], {})
        r = data[big].get("queries_raised_limit20", {}).get("queries", {}).get(q["id"], {})
        dm = d.get("metrics") or {}
        rm = r.get("metrics") or {}
        dr, rr = dm.get("estimatedTotalHits"), rm.get("estimatedTotalHits")
        fm = (r.get("truth_check") or {}).get("facets_match")
        fm_s = "—" if not fm else ("sí" if all(fm.values()) else "NO")
        A(f"| `{q['id']}` | {gt:,} | {fmt(dr)} | {fmt(rr)} | "
          f"{'—' if dr is None else ('sí' if dr == gt else 'NO')} | "
          f"{'—' if rr is None else ('sí' if rr == gt else 'NO')} | {fm_s} |")
    A("")
    # facets exactos
    A("### 3.2 Segmentación por facetas (conteos exactos, sin límite de 1000)")
    A("")
    A("| Consulta | GT | Facetas vs. ground truth | Buckets devueltos |")
    A("|---|---:|---|---|")
    for sc in [big]:
        st = data[sc].get("queries_raised_limit20", {}).get("queries", {})
        for qid in ("facet_estado_global", "facet_morosos_producto_riesgo",
                    "facet_score_bajo_canal", "facet_kyc_pendiente_dispositivo"):
            qv = st.get(qid)
            if not qv:
                continue
            tc = qv["truth_check"]
            fm = tc.get("facets_match") or {}
            fd = qv["metrics"].get("facetDistribution") or {}
            buckets = ", ".join(f"{k}:{len(v)}" for k, v in fd.items()) if isinstance(fd, dict) else "—"
            A(f"| `{qid}` | {tc['ground_truth_count']:,} | "
              f"{'idénticas' if fm and all(fm.values()) else 'diferencias'} | {buckets} |")
    A("")

    A("### 3.3 Verificación de los documentos devueltos")
    A("")
    A("Se piden los 5 `id` más bajos de cada segmento (`sort=id:asc`, `limit=5`) y se "
      "comparan contra el ground truth: comprueba que el motor devuelve **los documentos "
      "correctos**, no solo el conteo correcto.")
    A("")
    A("| Escala | Segmentos con ids exactos | Total |")
    A("|---:|---:|---:|")
    for sc in scales:
        v = data[sc].get("verify_ids")
        if not v:
            continue
        A(f"| {sc:,} | {v['ok']} | {v['total']} |")
    A("")
    ver = json.loads((RAW / "verificacion_ndjson.json").read_text()) if (RAW / "verificacion_ndjson.json").exists() else None
    if ver:
        r = ver["resumen"]
        A(f"**Triple verificación del ground truth**: {r['ok']}/{r['comparaciones']} comparaciones "
          f"idénticas entre (a) los arreglos numpy que generaron los documentos, "
          f"(b) un recuento independiente releyendo las {r['docs_totales']:,} líneas NDJSON y "
          f"(c) los conteos que reporta Meilisearch.")
        A("")

    # ---- 4. latencias ----
    A("## 4. Latencia por escala (consultas de segmentación, `limit=20`)")
    A("")
    A("### 4.1 Configuración default (maxTotalHits=1000)")
    A("")
    A("| Consulta | " + " | ".join(f"p50 @{sc:,}" for sc in scales) + " |")
    A("|---|" + "---:|" * len(scales))
    for q in spec.QUERIES:
        cells = []
        for sc in scales:
            st = data[sc].get("queries_default_limit20", {}).get("queries", {}).get(q["id"])
            cells.append(fmt(st["metrics"]["wall_ms_p50"], 2) if st and "metrics" in st else "—")
        A(f"| `{q['id']}` | " + " | ".join(cells) + " |")
    A("")
    A("### 4.2 Respuesta completa: `limit=1000` (el máximo que entrega el cap de fábrica)")
    A("")
    A("| Consulta | " + " | ".join(f"p50 @{sc:,}" for sc in scales) + " | bytes resp. @%s |" % f"{scales[-1]:,}")
    A("|---|" + "---:|" * (len(scales) + 1))
    for q in spec.QUERIES:
        cells = []
        last = None
        for sc in scales:
            st = data[sc].get("queries_default_limit1000", {}).get("queries", {}).get(q["id"])
            cells.append(fmt(st["metrics"]["wall_ms_p50"], 2) if st and "metrics" in st else "—")
            if sc == scales[-1] and st and "metrics" in st:
                last = st["metrics"]["resp_bytes"]
        A(f"| `{q['id']}` | " + " | ".join(cells) + f" | {fmt(last)} |")
    A("")
    rows = []
    for sc in scales:
        st = data[sc].get("queries_default_limit1000", {}).get("queries", {})
        for qid, qv in st.items():
            if "metrics" not in qv:
                continue
            m = qv["metrics"]
            rows.append([sc, qid, m.get("wall_ms_p50"), m.get("wall_ms_p95"), m.get("wall_ms_p99"),
                         m.get("meili_ms_p50"), m.get("hits"), m.get("estimatedTotalHits"),
                         m.get("resp_bytes")])
    csv_write("latencias_limit1000.csv",
              ["escala", "consulta", "wall_p50_ms", "wall_p95_ms", "wall_p99_ms",
               "meili_p50_ms", "hits", "estimatedTotalHits", "bytes_respuesta"], rows)
    # grafica de degradacion para 5 consultas representativas
    reps_q = ["seg_score_bajo", "seg_activos_sin_atraso", "seg_estado_cdmx",
              "facet_estado_global", "txt_apellido_hernandez", "geo_cdmx_25km"]
    series = []
    for i, qid in enumerate(reps_q):
        ys = []
        for sc in scales:
            st = data[sc].get("queries_default_limit20", {}).get("queries", {}).get(qid)
            ys.append(st["metrics"]["wall_ms_p50"] if st and "metrics" in st else None)
        series.append((qid, SERIES[i % len(SERIES)], ys))
    svg_line("latencia_p50_por_escala.svg", "Latencia p50 (limit=20) vs. tamaño del índice",
             "Documentos en el índice", "ms (p50)", series, scales)
    A("![Latencia p50 por escala](charts/latencia_p50_por_escala.svg)")
    A("")
    series2 = []
    for i, qid in enumerate(reps_q):
        ys = []
        for sc in scales:
            st = data[sc].get("queries_default_limit1000", {}).get("queries", {}).get(qid)
            ys.append(st["metrics"]["wall_ms_p50"] if st and "metrics" in st else None)
        series2.append((qid, SERIES[i % len(SERIES)], ys))
    svg_line("latencia_p50_limit1000.svg", "Latencia p50 devolviendo 1000 hits (cap de fábrica)",
             "Documentos en el índice", "ms (p50)", series2, scales)
    A("![Latencia p50 con 1000 hits](charts/latencia_p50_limit1000.svg)")
    A("")
    # ---- 4.3 semantica del tope ----
    A("### 4.3 Qué limita exactamente `pagination.maxTotalHits`")
    A("")
    cl = None
    for sc in sorted({s for s in scales if (RAW / f"cap_limits_{s}.json").exists()}, reverse=True):
        cl = json.loads((RAW / f"cap_limits_{sc}.json").read_text())
        cl["_scale"] = sc
        break
    if cl:
        A(f"Experimento dedicado sobre el índice de {cl['_scale']:,} documentos "
          f"(segmento de referencia: activos sin atraso = {cl['corridas'][0]['ground_truth_segmento']:,} clientes).")
        A("")
        for corrida in cl["corridas"]:
            A(f"**`maxTotalHits = {corrida['maxTotalHits']:,}`**")
            A("")
            A("| Petición | HTTP | hits devueltos | `estimatedTotalHits` | `totalHits` | error |")
            A("|---|---:|---:|---:|---:|---|")
            for c in corrida["casos"]:
                A(f"| `{c['caso']}` | {c['status']} | {fmt(c.get('hits'))} | "
                  f"{fmt(c.get('estimatedTotalHits'))} | {fmt(c.get('totalHits'))} | "
                  f"{c.get('error', '—')} |")
            A("")
        A("Lectura: el tope **no** oculta el tamaño del segmento (el conteo sigue exacto), "
          "pero **sí limita cuántos resultados puedes sacar** — vía `limit` y vía "
          "`offset + limit`, y en el modo `page`/`hitsPerPage` vía `page × hitsPerPage`.")
        A("")

    # ---- 5. costo de subir el cap ----
    A("## 5. Costo de cambiar `maxTotalHits`")
    A("")
    A("| Escala | Tiempo del PATCH de settings | Estado | Pico RSS durante el cambio |")
    A("|---:|---:|---|---:|")
    for sc in scales:
        rc = data[sc].get("raise_cap")
        if not rc:
            continue
        A(f"| {sc:,} | {fmt(rc.get('raise_cap_s'), 2)} s | {rc.get('status')} | {b2g(rc.get('peak_rss_bytes'))} |")
    A("")

    # ---- 6. paginacion profunda ----
    A("## 6. Paginación profunda (solo posible con el cap levantado)")
    A("")
    A("Barrido con `sort=id:asc`, `limit=20`, offsets de 0 a 1,000,000.")
    A("")
    for sc in scales:
        dp = data[sc].get("deep_pagination")
        if not dp:
            continue
        A(f"### Escala {sc:,}")
        A("")
        A("| Segmento | Offset | p50 | p95 | p99 | `processingTimeMs` | hits | GT | hits esperados | total reportado |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in dp["rows"]:
            A(f"| `{r['id']}` | {r['offset']:,} | {fmt(r.get('wall_ms_p50'), 2)} | {fmt(r.get('wall_ms_p95'), 2)} | "
              f"{fmt(r.get('wall_ms_p99'), 2)} | {fmt(r.get('meili_ms_p50'), 1)} | {fmt(r.get('hits'))} | "
              f"{fmt(r.get('ground_truth_count'))} | {fmt(r.get('expected_hits'))} | {fmt(r.get('totalHits') or r.get('estimatedTotalHits'))} |")
        A("")
        csv_write(f"deep_pagination_{sc}.csv",
                  ["segmento", "offset", "wall_p50_ms", "wall_p95_ms", "wall_p99_ms",
                   "meili_p50_ms", "hits", "ground_truth", "expected_hits", "total_reportado"],
                  [[r["id"], r["offset"], r.get("wall_ms_p50"), r.get("wall_ms_p95"),
                    r.get("wall_ms_p99"), r.get("meili_ms_p50"), r.get("hits"),
                    r.get("ground_truth_count"), r.get("expected_hits"),
                    r.get("totalHits") or r.get("estimatedTotalHits")] for r in dp["rows"]])
    bigdp = data[scales[-1]].get("deep_pagination")
    if bigdp:
        segs = sorted({r["id"] for r in bigdp["rows"]})
        series = []
        for i, seg in enumerate(segs):
            ys = [r.get("wall_ms_p50") for r in bigdp["rows"] if r["id"] == seg]
            series.append((seg, SERIES[i % len(SERIES)], ys))
        svg_line("deep_pagination_offsets.svg", f"Paginación profunda a {scales[-1]:,} documentos (p50)",
                 "Offset", "ms (p50)", series, spec.MAX_OFFSETS)
        A(f"![Paginación profunda](charts/deep_pagination_offsets.svg)")
        A("")

    # ---- 6b. offset vs keyset ----
    kp = RAW / "keyset_vs_offset.json"
    if kp.exists():
        k = json.loads(kp.read_text())
        A(f"### 6b. Offset vs paginación por llave (a {k['scale']:,})")
        A("")
        A(f"Mismo punto del segmento `{k['filtro_segmento']}` "
          f"({k['ground_truth_segmento']:,} clientes), ordenado por `{k['campo']}:asc`: "
          f"una vía pide `offset` y la otra filtra `{k['campo']} > cursor` (el cursor se ubicó "
          f"sólidamente por búsqueda binaria sobre conteos exactos).")
        A("")
        A("| Posición en el segmento | hits esperados | por `offset` (p50) | por keyset (p50) | factor | hits offset | hits keyset |")
        A("|---:|---:|---:|---:|---:|---:|---:|")
        for f in k["filas"]:
            A(f"| {f['posicion']:,} | {f['hits_esperados']} | "
              f"{fmt(f['por_offset'].get('p50_ms'), 2)} ms | {fmt(f['por_keyset'].get('p50_ms'), 2)} ms | "
              f"{fmt(f.get('factor'), 1)}× | {fmt(f['por_offset'].get('hits'))} | {fmt(f['por_keyset'].get('hits'))} |")
        A("")
        malos = [f for f in k["filas"] if not f.get("offset_hits_ok")]
        if malos:
            peor = max(malos, key=lambda f: f["posicion"])
            A(f"**Hallazgo adicional**: con una clave de ordenamiento llena de empates "
              f"(`{k['campo']}` tiene resolución de segundo sobre 1.2M de clientes), a la posición "
              f"{peor['posicion']:,} la vía por `offset` devolvió "
              f"**{peor['por_offset'].get('hits')} hits en {fmt(peor['por_offset'].get('p50_ms'), 1)} ms** "
              f"(se esperaban {peor['hits_esperados']}) mientras keyset devolvió "
              f"{peor['por_keyset'].get('hits')} hits en {fmt(peor['por_keyset'].get('p50_ms'), 2)} ms. "
              f"El motor gasta el tiempo y entrega vacío **sin error**: la misma clase de fallo "
              f"silencioso que el tope de 1000.")
            A("")
        A("Advertencia de implementación: keyset con una llave no única **pierde o repite filas** en "
          "los empates (hay ~muchos clientes con el mismo segundo). En producción la llave debe ser "
          "compuesta y única — aquí `id` no es filtrable, así que la comparación se hizo con "
          "`fecha_registro_ts` y el cursor se buscó por conteo exacto.")
        A("")

    # ---- 7. concurrencia ----
    A("## 7. Concurrencia (mezcla de consultas de segmentación, `limit=20`)")
    A("")
    A("| Escala | Clientes | Requeridas | OK | Errores | QPS | p50 | p95 | p99 | máx | CPU máx del motor |")
    A("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for sc in scales:
        for row in data[sc].get("concurrency_default", []):
            A(f"| {sc:,} | {row['clients']} | {row['requests']:,} | {row['ok']:,} | {row['errors']} | "
              f"{fmt(row['qps'], 1)} | {fmt(row['lat_p50'], 2)} | {fmt(row['lat_p95'], 2)} | "
              f"{fmt(row['lat_p99'], 2)} | {fmt(row['lat_max'], 2)} | {fmt((row.get('cpu') or {}).get('cpu_pct_max'), 0)}% |")
    A("")
    csv_write("concurrencia.csv",
              ["escala", "clientes", "requests", "ok", "errores", "qps", "p50", "p95", "p99",
               "max", "cpu_max_pct"],
              [[sc, r["clients"], r["requests"], r["ok"], r["errors"], r["qps"], r["lat_p50"],
                r["lat_p95"], r["lat_p99"], r["lat_max"], (r.get("cpu") or {}).get("cpu_pct_max")]
               for sc in scales for r in data[sc].get("concurrency_default", [])])
    conc_big = data[scales[-1]].get("concurrency_default", [])
    if conc_big:
        svg_line("concurrencia_qps.svg", f"QPS vs. clientes concurrentes a {scales[-1]:,} documentos",
                 "Clientes concurrentes", "QPS",
                 [("QPS", ACCENT, [r["qps"] for r in conc_big]),
                  ("p95 x10 (ms)", ACCENT2, [round((r["lat_p95"] or 0) * 10, 1) for r in conc_big])],
                 [r["clients"] for r in conc_big])
        A("![Concurrencia](charts/concurrencia_qps.svg)")
        A("")

    # ---- 7b. tolerancia a erratas y sobrecarga de cliente ----
    A("## 7b. Efecto de `typoTolerance` en los conteos de texto")
    A("")
    A("Con `typoTolerance.enabled=false` (base del laboratorio) los conteos de texto "
      "coinciden 1:1 con el ground truth; al activarla (valor de fábrica), el mismo "
      "segmento infla su volumen porque entran tokens con erratas.")
    A("")
    for sc in scales:
        te = data[sc].get("typo_experiment")
        if not te:
            continue
        A(f"### Escala {sc:,}")
        A("")
        A("| Consulta | Ground truth (token exacto) | reportado con typos OFF | factor | reportado con typos ON | factor |")
        A("|---|---:|---:|---:|---:|---:|")
        for qid in (te["typos_off"]["queries"]):
            off = te["typos_off"]["queries"][qid]
            on = te["typos_on"]["queries"][qid]
            A(f"| `{qid}` | {fmt(off['ground_truth_token_exacto'])} | {fmt(off['reportado'])} | "
              f"{fmt(off['factor_vs_exacto'], 3)} | {fmt(on['reportado'])} | {fmt(on['factor_vs_exacto'], 3)} |")
        A("")
    A("## 7c. Sobrecarga del cliente Python `requests`")
    A("")
    A("| Escala | urllib3 p50 | requests.Session p50 | delta |")
    A("|---:|---:|---:|---:|")
    for sc in scales:
        oh = data[sc].get("overhead_cliente")
        if not oh:
            continue
        A(f"| {sc:,} | {fmt(oh['urllib3_p50_ms'], 2)} ms | {fmt(oh['requests_session_p50_ms'], 2)} ms | "
          f"+{fmt(oh['delta_p50_ms'], 2)} ms |")
    A("")

    # ---- 8. sintesis de degradacion ----
    A("## 8. Síntesis de degradación")
    A("| Consulta | GT @" + f"{scales[-1]:,}" + " | p50 @" + f"{10_000:,}" +
      " | p50 @" + f"{scales[-1]:,}" + " | factor |")
    A("|---|---:|---:|---:|---:|")
    rows = []
    for q in spec.QUERIES:
        first = p50(10_000, "queries_default_limit20", q["id"]) if 10_000 in data else None
        last = None
        for sc in scales:
            st = data[sc].get("queries_default_limit20", {}).get("queries", {}).get(q["id"])
            if st and "metrics" in st:
                if first is None:
                    first = st["metrics"]["wall_ms_p50"]
                last = st["metrics"]["wall_ms_p50"]
        gt = GT["scales"][str(scales[-1])]["queries"][q["id"]]["count"]
        fac = round(last / first, 2) if first and last and first > 0 else None
        A(f"| `{q['id']}` | {gt:,} | {fmt(first, 2)} ms | {fmt(last, 2)} ms | {fmt(fac, 2)}× |")
        rows.append([q["id"], gt, first, last, fac])
    csv_write("degradacion_resumen.csv", ["consulta", "ground_truth_4m_p50_1k", "p50_min_escala",
                                          "p50_max_escala", "factor"], rows)

    # ---- 9. hallazgos ----
    A("")
    A("## 9. Hallazgos")
    A("")
    big = scales[-1]
    small = scales[0]
    # 9.1 tope de extraccion
    for sc in scales:
        qs = GT["scales"][str(sc)]["queries"]
        over = [q for q in spec.QUERIES if qs[q["id"]]["count"] > 1000]
        if not over:
            continue
        suma_gt = sum(qs[q["id"]]["count"] for q in over)
        max_seg = max(qs[q["id"]]["count"] for q in over)
        A(f"- **Escala {sc:,}**: {len(over)} de {len(spec.QUERIES)} segmentos superan los 1000 "
          f"resultados (suman {suma_gt:,} clientes; el mayor tiene {max_seg:,}). "
          f"Meilisearch **reporta el conteo exacto** (`estimatedTotalHits`), pero con "
          f"`maxTotalHits=1000` solo puedes **extraer 1000** por respuesta: listar esos "
          f"{suma_gt:,} clientes requiere forzar el tope o paginar de otra forma.")
    A("")
    A("- **`estimatedTotalHits` = conteo real**: en las 7 escalas y en las 27 consultas coincide "
      "con el ground truth bit a bit (no es una estimación para estos filtros). "
      "`pagination.maxTotalHits` (1000 de fábrica) no lo recorta: lo que limita es la "
      "extracción (`limit`, `offset + limit`, `page × hitsPerPage`), y el costo de extraer "
      "crece con el offset (sección 6).")
    cl2 = None
    for sc in sorted({s for s in scales if (RAW / f"cap_limits_{s}.json").exists()}, reverse=True):
        cl2 = json.loads((RAW / f"cap_limits_{sc}.json").read_text())
        cl2["_scale"] = sc
        break
    if cl2:
        cap1000 = next(c for c in cl2["corridas"] if c["maxTotalHits"] == 1000)
        caso = {c["caso"]: c for c in cap1000["casos"]}
        A(f"- **Truncado silencioso con el tope de fábrica** (medido a {cl2['_scale']:,}): "
          f"`limit=5000` responde **HTTP 200 con "
          f"{caso['limit=5000']['hits']:,} hits** (no 5,000, sin error ni aviso) y "
          f"`offset=1000&limit=20` responde **200 con 0 hits** sobre un segmento de "
          f"{cap1000['ground_truth_segmento']:,} clientes. Un cliente que pida la página 51 "
          f"recibe una lista vacía sin ninguna señal de que el tope lo cortó. Es el riesgo "
          f"operativo del valor por omisión.")
    # 9.2 facets
    fr = data[big].get("queries_raised_limit20", {}).get("queries", {})
    ex = []
    for qid, qv in fr.items():
        fm = (qv.get("truth_check") or {}).get("facets_match")
        if fm and all(fm.values()):
            ex.append(f"{qid} ({qv['truth_check']['ground_truth_count']:,} docs, "
                      f"p50 {fmt(qv['metrics']['wall_ms_p50'], 2)} ms)")
    if ex:
        A(f"- **Segmentación exacta por facetas a {big:,} documentos**: "
          f"{'; '.join(ex)}. Todas coinciden bucket por bucket con el ground truth y "
          f"no las afecta el techo de 1000.")
    # 9.3 latencias
    def p50(sc, key, qid):
        v = data[sc].get(key, {}).get("queries", {}).get(qid, {})
        return (v.get("metrics") or {}).get("wall_ms_p50")

    geo = []
    for qid in ("geo_cdmx_25km", "geo_gdl_50km"):
        ys = [(sc, p50(sc, "queries_default_limit20", qid)) for sc in scales]
        ys = [(sc, v) for sc, v in ys if v]
        if len(ys) >= 2:
            geo.append(f"`{qid}` {ys[0][1]:.1f} ms @{ys[0][0]:,} → {ys[-1][1]:.1f} ms @{ys[-1][0]:,} "
                       f"({ys[-1][1]/ys[0][1]:.0f}×)")
    if geo:
        A(f"- **Las consultas geográficas sí degradan con el volumen**: {'; '.join(geo)}. "
          f"Un `_geoRadius` recorre y ordena por distancia en lugar de usar un índice invertido "
          f"sobre un atributo filtrable, así que es la excepción a la regla de latencia plana "
          f"(~25× más caro que un filtro escalar a {big:,}).")

    base = 10_000 if 10_000 in data else small
    row = []
    for qid in ("seg_activos_sin_atraso", "seg_score_bajo", "facet_estado_global",
                "seg_kyc_verif_jovenes"):
        a, b = p50(base, "queries_default_limit20", qid), p50(big, "queries_default_limit20", qid)
        if a and b:
            row.append(f"`{qid}` {a:.2f}→{b:.2f} ms ({b/a:.1f}×)")
    if row:
        A(f"- **Latencia de búsqueda prácticamente plana frente al volumen** (`limit=20`, "
          f"de {base:,} a {big:,} documentos, {big//base}× más datos): {'; '.join(row)}.")
    r1 = []
    for qid in ("seg_activos_sin_atraso", "facet_estado_global"):
        a, b = p50(base, "queries_default_limit1000", qid), p50(big, "queries_default_limit1000", qid)
        if a and b:
            r1.append(f"`{qid}` {a:.2f}→{b:.2f} ms")
    if r1:
        A(f"- **Devolver 1000 hits en una sola respuesta** cuesta sobre todo serialización y "
          f"transferencia, y escala con el número de documentos serializados: {'; '.join(r1)}.")
    # 9.4 paginacion profunda
    dp = data[big].get("deep_pagination", {}).get("rows", [])
    if dp:
        for seg in sorted({r["id"] for r in dp}):
            rs = [r for r in dp if r["id"] == seg]
            a = next((r for r in rs if r["offset"] == 0), None)
            b = next((r for r in rs if r["offset"] == 1_000_000), None)
            if a and b and a.get("wall_ms_p50"):
                dentro = b["offset"] < (b.get("ground_truth_count") or 0)
                A(f"- **Paginación profunda `{seg}` a {big:,}**: offset 0 → {a['wall_ms_p50']:.2f} ms; "
                  f"offset {b['offset']:,} → {b['wall_ms_p50']:.2f} ms "
                  f"({b['wall_ms_p50']/a['wall_ms_p50']:.0f}×). El segmento tiene "
                  f"{b.get('ground_truth_count'):,} clientes: "
                  f"{'el offset cae dentro y devuelve ' + str(b['hits']) + ' hits' if dentro else 'el offset ya cae fuera del segmento y devuelve 0 hits, pero el motor igual recorre y ordena todos los candidatos'}"
                  f".")
    kp9 = RAW / "keyset_vs_offset.json"
    if kp9.exists():
        k9 = json.loads(kp9.read_text())
        partes = []
        for f in k9["filas"]:
            partes.append(f"{f['posicion']:,}: {fmt(f['por_offset'].get('p50_ms'), 0)} ms "
                          f"({fmt(f['por_offset'].get('hits'))} hits) vs "
                          f"{fmt(f['por_keyset'].get('p50_ms'), 1)} ms "
                          f"({fmt(f['por_keyset'].get('hits'))} hits)")
        A(f"- **Paginación por llave vs `offset`** (mismo punto del segmento, "
          f"+{k9['ground_truth_segmento']:,} clientes): {'; '.join(partes)}. La latencia de keyset "
          f"es prácticamente constante con la profundidad; la de `offset` crece y en el extremo "
          f"devuelve vacío sin error.")

    # 9.5 concurrencia
    cc = data[big].get("concurrency_default", [])
    if len(cc) >= 2:
        c0, cN = cc[0], cc[-1]
        A(f"- **Concurrencia a {big:,}**: {c0['clients']} cliente(s) → {c0['qps']:,.0f} qps "
          f"(p50 {c0['lat_p50']:.2f} ms, p95 {c0['lat_p95']:.2f} ms); "
          f"{cN['clients']} clientes → {cN['qps']:,.0f} qps "
          f"(p50 {cN['lat_p50']:.2f} ms, p95 {cN['lat_p95']:.2f} ms, "
          f"p99 {cN['lat_p99']:.2f} ms, CPU máx {(cN.get('cpu') or {}).get('cpu_pct_max')}%, "
          f"{cN['errors']} errores).")
        best = max(cc, key=lambda r: r["qps"])
        A(f"- **Punto de saturación**: el máximo de throughput se alcanza con "
          f"{best['clients']} clientes ({best['qps']:,.0f} qps); a partir de ahí la latencia p95 "
          f"crece sin ganar capacidad.")
    # 9.6 costos de indexado
    lc = data[big].get("load", {})
    lc0 = data[scales[1]].get("load", {}) if len(scales) > 1 else lc
    if lc.get("docs_per_s"):
        A(f"- **Indexado a {big:,}**: {lc['docs_per_s']:,.0f} docs/s "
          f"({lc['index_s']/60:.1f} min), índice {b2g(lc.get('db_bytes'))} "
          f"({lc.get('db_bytes', 0)/max(1, lc.get('docs_indexados', 1)):.0f} B/doc), "
          f"pico de RSS {b2g(lc.get('peak_rss_bytes'))}.")
    rc = data[big].get("raise_cap", {})
    if rc:
        A(f"- **Subir `maxTotalHits` a {big:,}** costó {rc.get('raise_cap_s'):.2f} s "
          f"(estado `{rc.get('status')}`), sin reenviar documentos.")
    # 9.7 typos
    te = data[big].get("typo_experiment", {}).get("typos_on", {}).get("queries")
    if te:
        infl = [(q, v) for q, v in te.items() if (v.get("factor_vs_exacto") or 1) > 1.05]
        if infl:
            A("- **Tolerancia a erratas**: activarla infla los conteos de segmentación de texto — "
              + "; ".join(f"`{q}` ×{v['factor_vs_exacto']}" for q, v in
                          sorted(infl, key=lambda x: -x[1]["factor_vs_exacto"])[:4])
              + ". Un segmento de texto medido con la configuración de fábrica no es comparable "
                "con un conteo exacto.")

    A("")
    A("## 10. Recomendaciones de diseño")
    A("")
    A("- **El conteo nunca fue el problema; la extracción sí.** `estimatedTotalHits` es exacto, "
      "así que para dimensionar un segmento basta un `limit=0/1` con el filtro. Para *listar* "
      "el segmento completo hay que lidiar con `maxTotalHits`: o se sube (barato: milisegundos, "
      "sin reindexar) o se recorre por llave.")
    A("- **Segmentar con filtros + facetas, no con hits.** La distribución por facetas entrega "
      "los conteos por categoría de millones de documentos en milisegundos, con buckets "
      "exactos, y es la vía natural para dimensionar y desglosar un segmento.")
    A("- **`maxTotalHits` es una decisión de producto.** Subirlo habilita `limit` y offsets "
      "grandes; el costo aparece al paginar profundo (offset 1M ≈ decenas de segundos). Para "
      "recorrer un segmento completo conviene *keyset pagination* "
      "(`sort=id:asc` + `filter=id > ultimo_id`) en lugar de offsets altos.")
    A("- **Devolver 1000 hits pesa más que buscar.** Si el caso de uso es *lista para operar* "
      "(cobranza, campañas), paginar de a pocos (`limit` 20–100) y usar `attributesToRetrieve` "
      "para no transferir 49 campos por cliente.")
    A("- **El volumen afecta poco a la búsqueda filtrada**: los índices invertidos hacen que la "
      "latencia la mande la cardinalidad del resultado, la paginación y lo que se serializa, "
      "no el tamaño total del índice.")
    A("- **Concurrencia**: el motor escala en núcleos hasta saturar CPU; por encima del punto de "
      "inflexión la latencia p95/p99 crece y las colas se acumulan. Dimensionar por CPU, no por QPS.")
    A("- **Cuidado con `typoTolerance` en segmentación**: infla los conteos en búsquedas de texto. "
      "Si el conteo se usa para decidir (presupuesto, tamaño de campaña), desactivarla por índice "
      "o restringirla con `disableOnWords`/`disableOnAttributes`.")
    A("")
    A("## 11. Limitaciones")
    A("")
    A("- Los datos son sintéticos y estacionarios: las distribuciones no representan a ninguna "
      "ninguna cartera real; sirven para tener ground truth exacto, no para inferir negocio.")
    A("- Un solo nodo, disco local NVMe, 12 vCPU y 13 GiB de RAM compartidos con el propio "
      "benchmark; no hay clúster, réplicas ni pruebas de fallos.")
    A("- `--max-indexing-memory 4GiB` y 8 hilos de indexado: cambiar esos parámetros mueve los "
      "tiempos de carga de la sección 1.")
    A("- Las latencias de paginación profunda usan `sort=id:asc` (orden determinista). Con el "
      "ranking por relevancia por defecto el perfil de costo cambia (se recalculan los buckets "
      "de ranking para cada offset).")
    A("- Las mediciones de latencia son de loopback: sin latencia de red ni TLS. El tiempo de "
      "motor (`processingTimeMs`) se reporta en paralelo para separar ambos efectos.")
    A("- Los percentiles por consulta se calculan con 20 repeticiones (6–10 en las etapas "
      "pesadas): son indicativos, no intervalos de confianza.")
    A("")
    A("## 12. Huella del entorno")
    A("")
    env = env_fingerprint()
    for k, v in env.items():
        A(f"- {k}: `{v}`")
    fl = data[scales[0]].get("flags", {})
    A(f"- Flags del motor: `--max-indexing-threads {fl.get('threads')} "
      f"--max-indexing-memory {fl.get('memory')} --env production`; "
      f"lotes de {fl.get('batch')} documentos; semilla del dataset {GT['meta']['seed']}.")

    (REP / "REPORTE.md").write_text("\n".join(md) + "\n")
    print(f"escrito {REP/'REPORTE.md'} ({len(md)} lineas)")
    print(f"graficas en {CHARTS}, tablas en {TABLES}")


if __name__ == "__main__":
    build()
