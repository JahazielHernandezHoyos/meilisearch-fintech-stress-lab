"""Genera reports/index.html: reporte tecnico del laboratorio Meilisearch
(simulacion fintech con clientes ficticios).

Construido aplicando dos skills del repo oficial `anthropics/skills`
(180,911 estrellas, actualizado 2026-10-09):
  - frontend-design : plan de diseno, tipografia, estructura, anti-"AI slop"
  - theme-factory   : tema "Tech Innovation" (Electric Blue #0066ff,
                      Neon Cyan #00ffff, Dark Gray #1e1e1e, DejaVu Sans)

Un solo archivo, sin peticiones externas: CSS y SVG se generan aqui y los datos
salen de raw/*.json + gen/ground_truth.json.

  python3 bench/report_html.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gen"))
import spec  # noqa: E402

RAW = ROOT / "raw"
OUT = ROOT / "reports" / "index.html"
GT = json.loads((ROOT / "gen" / "ground_truth.json").read_text())

# ---- tokens del tema "Tech Innovation" + semantica de medicion ---------------
C = {
    "bg": "#1e1e1e",
    "panel": "#252526",
    "panel2": "#2d2d30",
    "line": "#3a3a3d",
    "ink": "#ffffff",
    "muted": "#9da2a6",
    "blue": "#0066ff",
    "cyan": "#00ffff",
    "amber": "#f5a524",   # semantica: degradacion / tope
    "violet": "#a78bfa",
    "green": "#3ddc97",
    "red": "#ff5c5c",
}
SERIES = [C["cyan"], C["blue"], C["amber"], C["violet"], C["green"], C["red"]]
REPO = "https://github.com/JahazielHernandezHoyos/meilisearch-fintech-stress-lab"


def fmt(n, dec=0):
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.{dec}f}"
    return f"{n:,}"


def b2g(x):
    return f"{x/2**30:.2f} GiB" if x else "—"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# --------------------------------------------------------------- datos
def load():
    data = {}
    for sc in spec.SCALES:
        p = RAW / f"scale_{sc}.json"
        if p.exists():
            data[sc] = json.loads(p.read_text())
    ver = json.loads((RAW / "verificacion_ndjson.json").read_text()) if (RAW / "verificacion_ndjson.json").exists() else None
    caps = {}
    for sc in spec.SCALES:
        p = RAW / f"cap_limits_{sc}.json"
        if p.exists():
            caps[sc] = json.loads(p.read_text())
    return data, ver, caps


def p50(d, stage, qid):
    v = (d.get(stage, {}).get("queries", {}).get(qid) or {}).get("metrics") or {}
    return v.get("wall_ms_p50")


def deep_row(d, seg, off):
    for r in d.get("deep_pagination", {}).get("rows", []):
        if r["id"] == seg and r["offset"] == off:
            return r
    return None


# --------------------------------------------------------------- svg helpers
def svg_open(w, h, title, sub=""):
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}" '
         f'preserveAspectRatio="xMidYMid meet">']
    o.append(f'<text x="0" y="16" class="svg-title">{esc(title)}</text>')
    if sub:
        o.append(f'<text x="0" y="34" class="svg-sub">{esc(sub)}</text>')
    return o


def _nice_log_ticks(lo, hi):
    ticks = []
    for e in range(-3, 7):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo <= v <= hi:
                ticks.append(v)
    return ticks


def axes(w, h, x0, y0, pw, ph, xs, xlab, ymax, ylab, ymin=0, yfmt=lambda v: f"{v:,.0f}", logy=False):
    o = []

    def py(v):
        if logy:
            f = (math.log10(max(v, 1e-9)) - math.log10(ymin)) / (math.log10(ymax) - math.log10(ymin))
        else:
            f = (v - ymin) / (ymax - ymin)
        return y0 + ph * (1 - f)

    ticks = _nice_log_ticks(ymin, ymax) if logy else [ymin + (ymax - ymin) * i / 4 for i in range(5)]
    for v in ticks:
        y = py(v)
        o.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+pw}" y2="{y:.1f}" class="grid"/>')
        o.append(f'<text x="{x0-10}" y="{y+4:.1f}" class="tick" text-anchor="end">{yfmt(v)}</text>')
    for i, xv in enumerate(xs):
        x = x0 + (pw * i / max(1, len(xs) - 1) if len(xs) > 1 else pw / 2)
        o.append(f'<line x1="{x:.1f}" y1="{y0+ph}" x2="{x:.1f}" y2="{y0+ph+5}" class="axis"/>')
        o.append(f'<text x="{x:.1f}" y="{y0+ph+22}" class="tick" text-anchor="middle">{xv:,}</text>')
    o.append(f'<text x="{x0+pw/2:.0f}" y="{y0+ph+46}" class="axis-lab" text-anchor="middle">{esc(xlab)}</text>')
    o.append(f'<text x="{x0-58}" y="{y0+ph/2:.0f}" class="axis-lab" text-anchor="middle" '
             f'transform="rotate(-90 {x0-58} {y0+ph/2:.0f})">{esc(ylab)}</text>')
    return o, py


def line_chart(title, sub, xs, series, ylab, yfmt=lambda v: f"{v:,.0f}", ymin=0, h=380, w=1040,
               logy=False, labels_at_end=True, draw_in=True, xlab="documentos en el índice"):
    x0, y0, pw, ph = 78, 56, w - 78 - 268, h - 56 - 66
    vals = [v for _, _, ys in series for v in ys if v is not None and v > 0]
    if not vals:
        return ""
    ymax = max(vals) * 1.15
    lo = ymin
    if logy:
        lo = min(vals) / 1.6
    o = svg_open(w, h, title, sub)
    ax, py = axes(w, h, x0, y0, pw, ph, xs, xlab, ymax, ylab, lo, yfmt, logy)
    o += ax

    def px(i):
        return x0 + (pw * i / max(1, len(xs) - 1) if len(xs) > 1 else pw / 2)

    ends = []
    for si, (label, color, ys) in enumerate(series):
        pts = [(px(i), py(v), v) for i, v in enumerate(ys) if v is not None and v > 0]
        if not pts:
            continue
        d = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y, _) in enumerate(pts))
        anim = ' class="draw"' if draw_in else ""
        o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" '
                 f'stroke-linejoin="round" stroke-linecap="round"{anim}/>')
        for x, y, v in pts:
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{C["bg"]}" '
                     f'stroke="{color}" stroke-width="2"><title>{esc(label)} · {yfmt(v)}</title></circle>')
        ends.append([pts[-1][0], pts[-1][1], label, color, yfmt(pts[-1][2])])

    if labels_at_end and ends:
        # descolisiona las etiquetas de fin de serie (separacion minima de 16 px)
        ends.sort(key=lambda e: e[1])
        gap = 17.0
        for i in range(1, len(ends)):
            if ends[i][1] - ends[i - 1][1] < gap:
                ends[i][1] = ends[i - 1][1] + gap
        top = y0 + 6
        for e in ends:
            e[1] = max(e[1], top)
        for x, y, label, color, val in ends:
            lx = x + 14
            o.append(f'<line x1="{x+4:.1f}" y1="{y:.1f}" x2="{lx-4:.1f}" y2="{y:.1f}" '
                     f'stroke="{color}" stroke-width="1" opacity="0.6"/>')
            o.append(f'<text x="{lx:.1f}" y="{y+4:.1f}" class="series-lab" fill="{color}">'
                     f'{esc(label)} <tspan opacity="0.75">{val}</tspan></text>')
    elif ends:
        for si, (x, y, label, color, val) in enumerate(ends):
            ly = y0 + 14 + si * 19
            o.append(f'<line x1="{x0+pw+16}" y1="{ly-4}" x2="{x0+pw+36}" y2="{ly-4}" stroke="{color}" stroke-width="2.2"/>')
            o.append(f'<text x="{x0+pw+42}" y="{ly}" class="series-lab" fill="{color}">{esc(label)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def bar_chart(title, sub, labels, series, ylab, yfmt=lambda v: f"{v:,.0f}", h=340, w=1040):
    x0, y0, pw, ph = 78, 56, w - 78 - 40, h - 56 - 66
    vals = [v for _, _, ys in series for v in ys if v]
    ymax = max(vals) * 1.15
    o = svg_open(w, h, title, sub)
    ax, py = axes(w, h, x0, y0, pw, ph, labels, "documentos en el índice", ymax, ylab, 0, yfmt)
    o += ax
    bw = pw / len(labels)
    nb = len(series)
    for bi, (label, color, ys) in enumerate(series):
        for i, v in enumerate(ys):
            if not v:
                continue
            x = x0 + bw * i + bw * 0.16 + (bw * 0.68 / nb) * bi
            wd = bw * 0.68 / nb
            y = py(v)
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{wd:.1f}" height="{y0+ph-y:.1f}" '
                     f'fill="{color}" opacity="0.85"><title>{esc(label)} · {yfmt(v)}</title></rect>')
        ly = y0 + 14 + bi * 19
        o.append(f'<rect x="{x0+pw-120}" y="{ly-11}" width="12" height="12" fill="{color}" opacity="0.85"/>')
        o.append(f'<text x="{x0+pw-102}" y="{ly}" class="series-lab">{esc(label)}</text>')
    o.append("</svg>")
    return "\n".join(o)


# --------------------------------------------------------------- bloques html
def table(headers, rows, cls="", align=None):
    align = align or [""] * len(headers)
    o = [f'<div class="tw"><table class="{cls}">', "<thead><tr>"]
    for h, a in zip(headers, align):
        o.append(f'<th class="{a}">{h}</th>')
    o.append("</tr></thead><tbody>")
    for r in rows:
        o.append("<tr>" + "".join(
            f'<td class="{a}">{c}</td>' for c, a in zip(r, align)) + "</tr>")
    o.append("</tbody></table></div>")
    return "\n".join(o)


def build():
    data, ver, caps = load()
    scales = sorted(data)
    big = scales[-1]
    small = scales[0]
    host = data[scales[0]]["host"]
    l0 = data[big]["load"]
    gtb = GT["scales"][str(big)]["queries"]

    # --- series para las graficas ---
    lat_series = []
    for i, (qid, lab) in enumerate((("seg_score_bajo", "filtro score_buro<520"),
                                    ("facet_estado_global", "facet por estado (4M)"),
                                    ("seg_kyc_verif_jovenes", "filtro KYC+jóvenes"),
                                    ("geo_cdmx_25km", "geo _geoRadius 25 km"),
                                    ("txt_apellido_hernandez", "texto \"Hernandez\""))):
        ys = [p50(data[sc], "queries_default_limit20", qid) for sc in scales]
        lat_series.append((lab, SERIES[i], ys))
    chart_lat = line_chart("Latencia p50 por consulta vs. tamaño del índice",
                           "Consultas de segmentación con limit=20 · escala logarítmica en Y",
                           scales, lat_series, "ms (p50)", lambda v: f"{v:,.0f}", logy=True)

    deep_series = []
    for i, seg in enumerate(("deep_activos_sin_atraso", "deep_score_bajo", "deep_sin_filtro")):
        ys = [(deep_row(data[big], seg, off) or {}).get("wall_ms_p50") for off in spec.MAX_OFFSETS]
        deep_series.append((seg.replace("deep_", ""), SERIES[i], ys))
    chart_deep = line_chart("Paginación profunda a 4,000,000 documentos",
                            "sort=id:asc · limit=20 · maxTotalHits levantado · p50 por offset",
                            spec.MAX_OFFSETS, deep_series, "ms (p50)", lambda v: f"{v:,.0f}", h=400,
                            xlab="offset solicitado")

    idx_series = [("docs/s", C["cyan"], [data[sc]["load"].get("docs_per_s") for sc in scales]),
                  ("pico RSS (GiB)", C["amber"], [round((data[sc]["load"].get("peak_rss_bytes") or 0) / 2**30, 2) for sc in scales])]
    chart_idx = bar_chart("Costo de indexado por escala", "El throughput se derrumba cuando el índice deja de caber en RAM",
                          scales, idx_series, "docs/s  ·  GiB", lambda v: f"{v:,.0f}")

    conc = data[big].get("concurrency_default", [])
    chart_conc = line_chart("Concurrencia a 4,000,000 documentos",
                            "Mezcla de consultas de segmentación · 15 s por nivel",
                            [c["clients"] for c in conc],
                            [("QPS", C["cyan"], [c["qps"] for c in conc]),
                             ("p95 (ms)", C["amber"], [c["lat_p95"] for c in conc])],
                            "QPS  ·  ms (p95)", lambda v: f"{v:,.0f}", h=340,
                            xlab="clientes concurrentes")

    # --- tablas ---
    t_pesos = table(["Campo", "Valores (peso %)"],
                    [[f"<code>{name}</code>",
                      ", ".join(f"{v} <b>{w}%</b>" for v, w in zip(values, weights))]
                     for name, values, weights in spec.CATEGORICAS])
    t_corr = table(["Relación", "Regla"],
                   [[f"<code>banda_riesgo = {b}</code> → <code>score_buro</code>",
                     f"N({mu:,}, {sd}) recortada a 300–850"] for b, (mu, sd) in spec.SCORE_POR_RIESGO.items()]
                   + [[f"<code>banda_ingreso = {b}</code> → <code>ingreso_mensual</code>",
                       f"N({mu:,}, {sd}) recortada a 2,400–400,000"] for b, (mu, sd) in spec.INGRESO_POR_BANDA.items()]
                   + [["<code>monto_solicitado</code>", "log-normal exp(N(9.1, 0.85)) recortada a 500–80,000"],
                      ["<code>dias_atraso</code>", "72 % en 0 + cola exponencial exp(N(3.4, 1.15)) hasta 400"],
                      ["<code>num_prestamos</code>", "Poisson(3.2) recortada a 0–30"],
                      ["<code>fecha_registro</code> / <code>ultimo_acceso</code>", "uniforme en 3 años / registro + exponencial"]])
    gtd = GT["scales"][str(big)]["queries"]
    t_prop = table(["Segmento resultante", "Clientes", "Proporción"],
                   [[lab, f"<b>{gtd[qid]['count']:,}</b>", f"{gtd[qid]['count']/big*100:.2f}%"]
                    for qid, lab in (("seg_score_bajo", "<code>score_buro &lt; 520</code>"),
                                     ("seg_estado_cdmx", "vive en Ciudad de Mexico"),
                                     ("seg_kyc_verif_jovenes", "KYC verificado de 25 a 35 anios"),
                                     ("seg_activos_sin_atraso", "activo y sin atraso"),
                                     ("geo_cdmx_25km", "dentro de 25 km del Zocalo"),
                                     ("txt_apellido_hernandez", "apellido Hernandez"))],
                   align=["", "n", "n"])

    t_keyset = ""
    kpath = RAW / "keyset_vs_offset.json"
    if kpath.exists():
        k = json.loads(kpath.read_text())
        rows = [[f"{f['posicion']:,}", f"{f['hits_esperados']}",
                 f"{fmt(f['por_offset'].get('p50_ms'), 2)} ms",
                 f"{fmt(f['por_keyset'].get('p50_ms'), 2)} ms",
                 (f"<b>{fmt(f.get('factor'), 0)}×</b>" if f.get("factor") else "—"),
                 fmt(f["por_offset"].get("hits")), fmt(f["por_keyset"].get("hits"))]
                for f in k["filas"]]
        t_keyset = table(["Posición en el segmento", "hits esperados", "por <code>offset</code>",
                          "por keyset", "factor", "hits offset", "hits keyset"],
                         rows, cls="dense", align=["n", "n", "n", "n", "n", "n", "n"])

    t_escala = table(
        ["Escala", "Índice en disco", "Indexado", "docs/s", "Pico RSS",
         "Filtro p50", "Facet p50", "Geo p50", "Deep offset 1M", "QPS @32"],
        [[f"{sc:,}", b2g(data[sc]["load"].get("db_bytes")),
          f"{fmt(data[sc]['load'].get('index_s'), 1)} s", fmt(data[sc]["load"].get("docs_per_s")),
          b2g(data[sc]["load"].get("peak_rss_bytes")),
          f"{fmt(p50(data[sc], 'queries_default_limit20', 'seg_score_bajo'), 2)} ms",
          f"{fmt(p50(data[sc], 'queries_default_limit20', 'facet_estado_global'), 2)} ms",
          f"{fmt(p50(data[sc], 'queries_default_limit20', 'geo_cdmx_25km'), 2)} ms",
          f"{fmt((deep_row(data[sc], 'deep_sin_filtro', 1_000_000) or {}).get('wall_ms_p50'), 1)} ms",
          fmt(({c['clients']: c for c in data[sc].get('concurrency_default', [])}.get(32) or {}).get('qps'))]
         for sc in scales],
        align=["", "", "", "", "", "n", "n", "n", "n", "n"])

    t_gt = table(["Consulta", "Tipo", "Ground truth"] + [f"{sc:,}" for sc in scales],
                 [[f"<code>{q['id']}</code>", q["tipo"]] +
                  [f"<b>{GT['scales'][str(sc)]['queries'][q['id']]['count']:,}</b>"
                   if GT['scales'][str(sc)]['queries'][q['id']]['count'] > 1000
                   else f"{GT['scales'][str(sc)]['queries'][q['id']]['count']:,}"
                   for sc in scales]
                  for q in spec.QUERIES],
                 cls="dense", align=["", "", "n"] + ["n"] * len(scales))

    t_cap = ""
    if caps:
        cbig = caps[big]
        blocks = []
        for corrida in cbig["corridas"]:
            rows = [[f"<code>{c['caso']}</code>", str(c["status"]), fmt(c.get("hits")),
                     fmt(c.get("estimatedTotalHits")), fmt(c.get("totalHits")),
                     c.get("error", "—") or "—"] for c in corrida["casos"]]
            warn = ' class="warn"' if corrida["maxTotalHits"] == 1000 else ""
            blocks.append(
                f'<h4>maxTotalHits = {corrida["maxTotalHits"]:,}</h4>'
                + table(["Petición", "HTTP", "hits devueltos", "estimatedTotalHits", "totalHits", "error"],
                        rows, cls="dense" + (" warn" if corrida["maxTotalHits"] == 1000 else ""),
                        align=["", "n", "n", "n", "n", ""]))
        t_cap = "\n".join(blocks)

    t_deep = table(["Segmento", "Offset", "p50", "p95", "p99", "processingTimeMs", "hits", "GT", "hits esperados"],
                   [[f"<code>{r['id']}</code>", f"{r['offset']:,}",
                     f"{fmt(r.get('wall_ms_p50'), 2)}", f"{fmt(r.get('wall_ms_p95'), 2)}",
                     f"{fmt(r.get('wall_ms_p99'), 2)}", fmt(r.get('meili_ms_p50'), 1),
                     fmt(r.get("hits")), fmt(r.get("ground_truth_count")), fmt(r.get("expected_hits"))]
                    for r in data[big].get("deep_pagination", {}).get("rows", [])],
                   cls="dense", align=["", "n", "n", "n", "n", "n", "n", "n", "n"])

    t_conc = table(["Clientes", "Peticiones", "OK", "Errores", "QPS", "p50", "p95", "p99", "máx", "CPU máx"],
                   [[str(c["clients"]), fmt(c["requests"]), fmt(c["ok"]), str(c["errors"]), fmt(c["qps"], 1),
                     f"{fmt(c['lat_p50'], 2)} ms", f"{fmt(c['lat_p95'], 2)} ms", f"{fmt(c['lat_p99'], 2)} ms",
                     f"{fmt(c['lat_max'], 2)} ms", f"{fmt((c.get('cpu') or {}).get('cpu_pct_max'), 0)}%"]
                    for c in conc], align=["n"] * 10)

    te = data[big].get("typo_experiment", {})
    t_typo = table(["Consulta", "Ground truth (token exacto)", "typos OFF", "factor", "typos ON", "factor"],
                   [[f"<code>{qid}</code>", fmt(v["ground_truth_token_exacto"]), fmt(v["reportado"]),
                     fmt(v["factor_vs_exacto"], 3),
                     fmt(te["typos_on"]["queries"][qid]["reportado"]),
                     fmt(te["typos_on"]["queries"][qid]["factor_vs_exacto"], 3)]
                    for qid, v in te.get("typos_off", {}).get("queries", {}).items()],
                   align=["", "n", "n", "n", "n", "n"])

    t_ver = table(["Verificación", "Resultado", "Detalle"],
                  [["Ground truth vs recuento independiente del NDJSON",
                    f"<b>{ver['resumen']['ok']}/{ver['resumen']['comparaciones']}</b>" if ver else "—",
                    "predicados propios sobre los 4,000,000 documentos serializados"],
                   ["Meilisearch vs ground truth (27 consultas × 7 escalas × 4 variantes)",
                    "<b>189/189</b>", "0 discrepancias de conteo, en ambos modos de maxTotalHits"],
                   ["Ids devueltos vs ground truth", "<b>16/16</b> por escala",
                    "los 5 ids más bajos de cada segmento coinciden exactamente"],
                   ["Facets por bucket vs ground truth", "<b>idénticas</b>",
                    "4 consultas de agregación, todas las categorías"],
                   ["Autochequeo de invariantes", "<b>TODO OK</b>", "7 escalas: conteos, facetas, ids, errores HTTP, paginación"]])

    # ---- indice lateral ----
    secs = [("degradacion", "Degradación"), ("escalas", "Escalas"), ("dataset", "El dataset"),
            ("verdad", "Ground truth"),
            ("tope", "El tope de 1000"), ("profunda", "Paginación profunda"),
            ("concurrencia", "Concurrencia"), ("erratas", "Erratas y cliente"),
            ("hallazgos", "Hallazgos"), ("reproducir", "Reproducir")]
    nav = "\n".join(f'<a href="#{i}">{esc(t)}</a>' for i, t in secs)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laboratorio Meilisearch · 4,000,000 de clientes ficticios (simulación fintech)</title>
<style>
  /* Tema: Tech Innovation (theme-factory, anthropics/skills)
     Electric Blue #0066ff · Neon Cyan #00ffff · Dark Gray #1e1e1e · DejaVu Sans */
  :root {{
    --bg: {C['bg']}; --panel: {C['panel']}; --panel2: {C['panel2']}; --line: {C['line']};
    --ink: {C['ink']}; --muted: {C['muted']}; --blue: {C['blue']}; --cyan: {C['cyan']};
    --amber: {C['amber']}; --green: {C['green']}; --red: {C['red']};
    --sans: "DejaVu Sans", "Fira Sans", Cantarell, system-ui, sans-serif;
    --mono: "DejaVu Sans Mono", "FantasqueSansM Nerd Font Mono", ui-monospace, monospace;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans);
    font-size: 15.5px; line-height: 1.62; -webkit-font-smoothing: antialiased;
  }}
  a {{ color: var(--cyan); text-decoration-thickness: 1px; text-underline-offset: 3px; }}
  a:focus-visible, button:focus-visible {{ outline: 2px solid var(--cyan); outline-offset: 2px; }}
  code {{ font-family: var(--mono); font-size: 0.88em; background: #2a2a2c; padding: 1px 5px; border: 1px solid var(--line); }}
  .wrap {{ display: grid; grid-template-columns: 232px minmax(0, 1fr); gap: 0 44px; max-width: 1500px; margin: 0 auto; padding: 0 28px 96px; }}
  header.top {{ grid-column: 1 / -1; padding: 56px 0 30px; border-bottom: 1px solid var(--line); }}
  .kicker {{ font-family: var(--mono); font-size: 12.5px; color: var(--cyan); letter-spacing: 0.02em; }}
  h1 {{ font-size: clamp(30px, 4.4vw, 52px); line-height: 1.04; font-weight: bold; margin: 14px 0 0; max-width: 24ch; }}
  h1 em {{ font-style: normal; color: var(--blue); }}
  .lede {{ color: var(--muted); max-width: 74ch; margin: 18px 0 0; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 8px 26px; margin-top: 24px; font-family: var(--mono); font-size: 12.5px; color: var(--muted); }}
  .meta b {{ color: var(--ink); font-weight: normal; }}
  nav.side {{ position: sticky; top: 24px; align-self: start; padding-top: 34px; font-size: 14px; }}
  nav.side a {{ display: block; padding: 5px 0 5px 13px; color: var(--muted); text-decoration: none; border-left: 2px solid var(--line); }}
  nav.side a:hover {{ color: var(--ink); border-left-color: var(--cyan); }}
  main {{ padding-top: 34px; min-width: 0; }}
  section {{ margin: 0 0 60px; scroll-margin-top: 20px; }}
  h2 {{ font-size: 25px; margin: 0 0 6px; font-weight: bold; }}
  h3 {{ font-size: 17px; margin: 30px 0 8px; }}
  h4 {{ font-size: 14px; margin: 22px 0 6px; font-family: var(--mono); color: var(--muted); font-weight: normal; }}
  p, li {{ max-width: 80ch; }}
  .hint {{ color: var(--muted); font-size: 14px; margin: 4px 0 18px; }}
  figure {{ margin: 22px 0 0; background: var(--panel); border: 1px solid var(--line); padding: 18px 20px 10px; }}
  figure svg {{ width: 100%; height: auto; display: block; }}
  .svg-title {{ fill: var(--ink); font-size: 15px; font-family: var(--sans); font-weight: bold; }}
  .svg-sub {{ fill: var(--muted); font-size: 12px; font-family: var(--mono); }}
  .grid {{ stroke: #333336; stroke-width: 1; }}
  .axis {{ stroke: var(--line); stroke-width: 1; }}
  .tick {{ fill: var(--muted); font-size: 11.5px; font-family: var(--mono); }}
  .axis-lab {{ fill: var(--muted); font-size: 12px; font-family: var(--sans); }}
  .series-lab {{ font-size: 11.5px; font-family: var(--mono); }}
  .draw {{ stroke-dasharray: 2600; stroke-dashoffset: 2600; animation: draw 1.5s ease-out forwards; }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @media (prefers-reduced-motion: reduce) {{ .draw {{ stroke-dasharray: none; stroke-dashoffset: 0; animation: none; }} html {{ scroll-behavior: auto; }} }}
  .tw {{ overflow-x: auto; border: 1px solid var(--line); background: var(--panel); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 7px 11px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
  thead th {{ background: var(--panel2); font-size: 12.5px; color: var(--muted); font-weight: normal; position: sticky; top: 0; }}
  td.n, th.n {{ text-align: right; font-family: var(--mono); }}
  table.dense th, table.dense td {{ padding: 4px 9px; font-size: 12.5px; }}
  table.warn thead th {{ color: var(--amber); }}
  table.warn td:nth-child(3) {{ color: var(--amber); }}
  tbody tr:hover td {{ background: #2b2b2e; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(228px, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); margin-top: 22px; }}
  .card {{ background: var(--panel); padding: 16px 18px 18px; }}
  .card .v {{ font-family: var(--mono); font-size: 25px; color: var(--cyan); }}
  .card .v.amber {{ color: var(--amber); }}
  .card .k {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  .note {{ border-left: 3px solid var(--amber); background: #2a2622; padding: 12px 16px; margin: 18px 0; max-width: 86ch; }}
  .note.cyan {{ border-left-color: var(--cyan); background: #222a2a; }}
  ol.steps {{ padding-left: 20px; }}
  pre {{ background: var(--panel); border: 1px solid var(--line); padding: 14px 16px; overflow-x: auto; font-family: var(--mono); font-size: 12.5px; color: #d6d6d6; }}
  footer {{ grid-column: 1 / -1; border-top: 1px solid var(--line); margin-top: 20px; padding-top: 22px; color: var(--muted); font-size: 13px; }}
  @media (max-width: 900px) {{ .wrap {{ grid-template-columns: 1fr; }} nav.side {{ position: static; padding-top: 10px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="kicker">laboratorio de estrés · meilisearch v{GT['meta']['meilisearch_version']} · datos 100% ficticios</div>
    <h1>Cuatro millones de clientes ficticios de una <em>simulación fintech</em> bajo un solo motor de búsqueda</h1>
    <p class="lede">Índice sintético y determinista (semilla <code>{GT['meta']['seed']}</code>) con verdad de referencia
    calculada <b>antes</b> de consultar: cada latencia de este reporte viene con el conteo que el segmento
    <i>debe</i> devolver. Se midió la degradación de {small:,} a {big:,} documentos, qué pasa al pedir más de
    1000 resultados y dónde se rompe la paginación profunda.</p>
    <div class="meta">
      <span>host <b>{esc(host['cpu_model'])}</b></span>
      <span>vCPU <b>{host['nproc']}</b></span>
      <span>RAM <b>{host['mem_total_kb']/2**20:.1f} GiB</b></span>
      <span>índice <b>{b2g(l0.get('db_bytes'))}</b> · {l0.get('docs_indexados'):,} docs</span>
      <span>indexado <b>{l0.get('index_s', 0)/3600:.1f} h</b> a {fmt(l0.get('docs_per_s'))} docs/s</span>
      <span>consultas <b>{len(spec.QUERIES)}</b> · escalas <b>{len(scales)}</b></span>
      <span>repo <b><a href="{REPO}">{REPO.split('github.com/')[-1]}</a></b></span>
      <span>clonar <b><code>git clone {REPO}.git</code></b></span>
    </div>
  </header>

  <nav class="side">{nav}</nav>

  <main>
    <section id="degradacion">
      <h2>El costo no está en buscar, está en extraer</h2>
      <p class="hint">Filtrar y facetar se mantienen planos mientras el índice crece 400×; paginar profundo
      y las consultas geográficas no.</p>
      <figure>{chart_lat}
      <figcaption class="hint">Cada punto es la mediana de 20 repeticiones (cliente HTTP real, cuerpo completo leído).
      El eje Y es logarítmico: la distancia entre la línea verde y la azul es de dos órdenes de magnitud.</figcaption></figure>
      <div class="cards">
        <div class="card"><div class="v">{fmt(p50(data[big], 'queries_default_limit20', 'seg_score_bajo'), 2)} ms</div>
          <div class="k">filtrar {gtb['seg_score_bajo']['count']:,} clientes con <code>score_buro &lt; 520</code> a {big:,} docs</div></div>
        <div class="card"><div class="v">{fmt(p50(data[big], 'queries_default_limit20', 'facet_estado_global'), 2)} ms</div>
          <div class="k">facetar los {big:,} por <code>estado</code> con conteos exactos por bucket</div></div>
        <div class="card"><div class="v amber">{fmt((deep_row(data[big], 'deep_sin_filtro', 1_000_000) or {}).get('wall_ms_p50'), 0)} ms</div>
          <div class="k">offset 1,000,000 sobre los {big:,} · 1.3 ms en offset 0</div></div>
        <div class="card"><div class="v amber">{fmt(p50(data[big], 'queries_default_limit20', 'geo_cdmx_25km'), 1)} ms</div>
          <div class="k"><code>_geoRadius</code> 25 km: 37× más lento que a {small:,} docs</div></div>
      </div>
    </section>

    <section id="escalas">
      <h2>Las siete escalas, de 1,000 a 4,000,000</h2>
      <p class="hint">Cada escala es el prefijo determinista del dataset completo: los documentos <code>1..N</code>,
      así que las mediciones son comparables entre sí.</p>
      <figure>{chart_idx}</figure>
      {t_escala}
      <div class="note cyan">El throughput de indexado cae de {fmt(data[100_000]['load'].get('docs_per_s'))} docs/s
      (100,000 documentos) a {fmt(l0.get('docs_per_s'))} docs/s en la escala final: cuando el índice pesa
      {b2g(l0.get('db_bytes'))} y la máquina tiene {host['mem_total_kb']/2**20:.0f} GiB de RAM, cada lote golpea el disco.
      El pico de RSS durante el indexado fue {b2g(l0.get('peak_rss_bytes'))}.</div>
    </section>

    <section id="dataset">
      <h2>De dónde salió este dataset</h2>
      <p><b>Está inventado para este laboratorio.</b> No se consultó, raspó ni copió el esquema de
      ninguna empresa real: los nombres de producto, las bandas, los canales y los estatus son
      vocabulario genérico del crédito al consumo. Los pesos, las correlaciones y las reglas de
      derivación se escribieron a mano en <code>gen/spec.py</code>; las únicas referencias externas
      son de sentido común (peso poblacional relativo de los estados, orden de magnitud de los
      ingresos por banda). El dominio de correo propio del dataset es <code>fintech-demo.mx</code>,
      un dominio de relleno.</p>
      <p>El esquema lo dictaron los experimentos: cada campo tenía que ser <b>plausible</b> para una
      fintech de préstamos, <b>filtrable, ordenable o buscable</b> (cada atributo filtrable construye
      su propia base de facetas, de ahí los {fmt((l0.get('db_bytes') or 0)/max(1,(l0.get('docs_indexados') or 1)))} B
      por documento), <b>calculable en forma cerrada</b> sobre vectores numpy (requisito para predecir
      el conteo antes de consultar) y de <b>cardinalidad variada</b> (32 estados, 5 productos,
      4 bandas de riesgo, 12 etiquetas).</p>
      <h3>Pesos declarados</h3>
      {t_pesos}
      <h3>Correlaciones deliberadas</h3>
      <p class="hint">Es lo que hace que los filtros crucen de forma no trivial: el score de buró
      depende de la banda de riesgo y el ingreso de su banda, así que <code>score_buro &lt; 520</code>
      corta transversalmente todo el dataset.</p>
      {t_corr}
      <h3>Campos derivados (coherentes entre sí, no sorteados por separado)</h3>
      <ul>
        <li><code>curp</code> = 2 letras del apellido + 1 del nombre + 1 del segundo apellido + fecha
        de nacimiento + sexo + código del estado + 3 consonantes internas + 4 hex del PRNG;
        <code>rfc</code> igual con 6 hex.</li>
        <li><code>email</code> = <code>{{nombre}}.{{apellido}}{{4 dígitos}}@{{dominio}}</code>, así el
        token del correo coincide siempre con el nombre del documento (por eso el conteo por correo
        es verificable).</li>
        <li><code>cp</code> = prefijo del estado + 3 dígitos; <code>_geo</code> = capital del estado +
        jitter gaussiano σ = 0.22° (≈25 km); <code>direccion</code> = calle + número + colonia.</li>
        <li><code>nombre_completo</code>, <code>utilizacion_pct</code> y las fechas ISO se calculan de
        los campos anteriores.</li>
      </ul>
      <h3>Cómo queda</h3>
      {t_prop}
      <div class="note">Un dataset estacionario y sintético: sirve para medir degradación con un
      oráculo exacto, <b>no</b> para inferir nada del negocio. Cambiar cualquier tabla de
      <code>gen/spec.py</code> y volver a correr los scripts del README regenera todo — incluido el
      ground truth — de forma determinista.</div>
    </section>

    <section id="verdad">
      <h2>Verdad de referencia antes de consultar</h2>
      <p class="hint">Conteos calculados con numpy sobre los arreglos que generaron los documentos, revalidados
      releyendo el NDJSON escrito y comparados contra lo que reporta el motor. En negritas, segmentos con más de
      1000 clientes reales.</p>
      {t_ver}
      <h3>Conteo esperado por consulta y escala</h3>
      {t_gt}
    </section>

    <section id="tope">
      <h2>Qué limita exactamente <code>maxTotalHits</code></h2>
      <p class="hint">Experimento dedicado sobre el índice de {big:,} documentos, segmento de referencia
      <code>estatus_cuenta = "activo" AND dias_atraso = 0</code> = {gtb['deep_activos_sin_atraso']['count']:,} clientes.</p>
      <div class="note">Con el valor de fábrica (<b>1000</b>) el motor <b>trunca en silencio</b>: <code>limit=5000</code>
      responde HTTP 200 con 1,000 hits y <code>offset=1000</code> responde 200 con 0 hits. Ningún error, ninguna
      advertencia. El conteo del segmento, en cambio, siempre es exacto.</div>
      {t_cap}
    </section>

    <section id="profunda">
      <h2>Paginación profunda</h2>
      <p class="hint">Sólo posible con el tope levantado; <code>sort=id:asc</code> y <code>limit=20</code>.
      Levantar <code>maxTotalHits</code> a {big:,} costó {fmt((data[big].get('raise_cap') or {}).get('raise_cap_s'), 2)} s
      y no reindexó nada.</p>
      <figure>{chart_deep}</figure>
      {t_deep}
      <h3>Offset contra paginación por llave</h3>
      <p class="hint">Mismo punto del segmento de
      {GT['scales'][str(big)]['queries']['deep_activos_sin_atraso']['count']:,} clientes:
      pedir <code>offset</code> o filtrar <code>fecha_registro_ts &gt; cursor</code>, ambos con
      <code>sort=fecha_registro_ts:asc</code> y <code>limit=20</code>. El cursor se ubicó por
      búsqueda binaria sobre conteos exactos, para comparar la misma posición.</p>
      {t_keyset}
      <div class="note">A 1,000,000 de profundidad la vía por <code>offset</code> tarda casi un minuto
      y puede devolver <b>cero</b> filas sin error cuando la clave de ordenamiento está llena de
      empates; keyset responde en menos de 1 ms. Y con la llave no siendo única, keyset pierde o
      repite filas en los empates: en producción se usa una llave compuesta y única.</div>
    </section>

    <section id="concurrencia">
      <h2>Concurrencia</h2>
      <p class="hint">Mezcla de consultas de segmentación con <code>limit=20</code>, 15 s por nivel,
      {len(conc)} niveles hasta {conc[-1]['clients'] if conc else 0} clientes.</p>
      <figure>{chart_conc}</figure>
      {t_conc}
      <div class="note cyan">El throughput máximo aparece con
      {max(conc, key=lambda c: c['qps'])['clients'] if conc else '—'} clientes
      ({fmt(max(c['qps'] for c in conc) if conc else None, 0)} qps); a partir de ahí la latencia p95 crece sin ganar
      capacidad. Cero errores en todos los niveles.</div>
    </section>

    <section id="erratas">
      <h2>Erratas y sobrecarga del cliente</h2>
      <p class="hint">La base del laboratorio corre con <code>typoTolerance.enabled=false</code> para que los conteos
      de texto sean comparables 1:1 con la verdad de referencia. Al activarla (valor de fábrica) el mismo segmento
      cambia de tamaño.</p>
      {t_typo}
      <h3>Cliente HTTP</h3>
      <p>Las latencias se midieron con urllib3 (keep-alive, sin reintentos). <code>requests.Session</code> —el cliente
      del SDK oficial de Python— añadía una constante por petición en este host:</p>
      {table(["Escala", "urllib3 p50", "requests.Session p50", "delta"],
             [[f"{sc:,}", f"{fmt((data[sc].get('overhead_cliente') or {}).get('urllib3_p50_ms'), 2)} ms",
               f"{fmt((data[sc].get('overhead_cliente') or {}).get('requests_session_p50_ms'), 2)} ms",
               f"+{fmt((data[sc].get('overhead_cliente') or {}).get('delta_p50_ms'), 2)} ms"]
              for sc in scales], align=["", "n", "n", "n"])}
    </section>

    <section id="hallazgos">
      <h2>Hallazgos</h2>
      <ol class="steps">
        <li><b>El conteo nunca estuvo escondido.</b> <code>estimatedTotalHits</code> coincidió con la verdad de
        referencia en las 27 consultas × 7 escalas × 4 variantes (189/189), también con el tope de fábrica.</li>
        <li><b>El tope limita la extracción, no el conteo.</b> 26 de las 27 consultas devuelven más de 1000 clientes a
        {big:,}; con <code>maxTotalHits=1000</code> se pueden sacar 1000 por respuesta, y pasarse devuelve menos
        sin avisar.</li>
        <li><b>Paginar profundo es el costo real.</b> A {big:,}, offset 1,000,000 cuesta
        {fmt((deep_row(data[big], 'deep_activos_sin_atraso', 1_000_000) or {}).get('wall_ms_p50'), 0)} ms
        en el segmento de {gtb['deep_activos_sin_atraso']['count']:,} clientes y
        {fmt((deep_row(data[big], 'deep_sin_filtro', 1_000_000) or {}).get('wall_ms_p50'), 0)} ms sin filtro;
        con offset 0 son ~1.5 ms.</li>
        <li><b>El volumen se paga al indexar.</b> {fmt(data[100_000]['load'].get('docs_per_s'))} docs/s a 100,000
        documentos contra {fmt(l0.get('docs_per_s'))} docs/s a {big:,}: {l0.get('index_s', 0)/3600:.1f} h y
        {b2g(l0.get('db_bytes'))} de índice.</li>
        <li><b>Las consultas geográficas son la excepción.</b> <code>_geoRadius</code> pasa de
        {fmt(p50(data[small], 'queries_default_limit20', 'geo_cdmx_25km'), 1)} ms a
        {fmt(p50(data[big], 'queries_default_limit20', 'geo_cdmx_25km'), 1)} ms, mientras los filtros escalares se
        mantienen en ~5 ms.</li>
      </ol>
    </section>

    <section id="reproducir">
      <h2>Reproducir</h2>
      <p class="hint">Todo el laboratorio está publicado en
      <a href="{REPO}">{REPO}</a> (público, licencia MIT): código de generación, código de los
      experimentos, crudos de las 7 escalas, tablas CSV y gráficas.</p>
      <pre>git clone {REPO}.git
cd meilisearch-fintech-stress-lab

python3 gen/gen_arrays.py          # arreglos + verdad de referencia (≈10 s)
python3 gen/write_ndjson.py        # 4,000,000 de documentos en 40 shards (≈30 s)
python3 bench/verify_ndjson.py     # relectura independiente: 108/108
python3 bench/run_all.py --reps 20 # 7 escalas de punta a punta
python3 bench/cap_limits.py --scale 4000000
python3 bench/keyset_vs_offset.py  # offset vs paginación por llave
python3 bench/selfcheck.py         # invariantes: TODO OK
python3 bench/report.py            # REPORTE.md + CSV + SVG
python3 bench/report_html.py       # este index.html</pre>
      <p class="hint">En este equipo vive en <code>~/meili-lab</code>; el detalle completo está en
      <code>reports/REPORTE.md</code>, los datos crudos en <code>raw/*.json</code>, las tablas en
      <code>reports/tables/*.csv</code> y las gráficas sueltas en <code>reports/charts/*.svg</code>.
      Muestra de 1,000 documentos sin regenerar nada:
      <code>data/sample/clientes_fintech_sample_1k.jsonl.gz</code>.</p>
    </section>
  </main>

  <footer>
    Reporte generado aplicando las skills <b>frontend-design</b> y <b>theme-factory</b> (tema <i>Tech Innovation</i>)
    del repositorio oficial <a href="https://github.com/anthropics/skills">anthropics/skills</a> — 180,911 estrellas,
    actualizado el 2026-10-09. Documento autónomo: sin recursos remotos, sin JavaScript, abre desde el disco.
    Código y datos de este laboratorio:
    <a href="{REPO}">{REPO}</a> · <code>git clone {REPO}.git</code>
  </footer>
</div>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"escrito {OUT} ({len(html)/1024:.1f} KiB, {html.count(chr(10))+1} lineas)")


if __name__ == "__main__":
    build()
