# Laboratorio de estrés: Meilisearch con 4,000,000 de clientes ficticios (simulación fintech)

Laboratorio reproducible de **degradación y segmentación** sobre **Meilisearch v1.55.0** con un
dataset sintético de **4 millones de usuarios** de una **simulación fintech** de crédito al consumo.

Todo el contenido es **fake y determinista** (semilla `20261013`): nombres, teléfonos, CURP, RFC,
montos, coordenadas y fechas se generan por software. No corresponden a personas ni carteras reales.

El punto central: **antes** de consultar a Meilisearch ya se sabe cuántos resultados debe devolver
cada segmento (verdad de referencia calculada con numpy sobre los mismos arreglos que generan los
documentos), así que cada medición de latencia viene acompañada de una verificación de conteo.

## Resultados principales

| Hallazgo | Evidencia |
|---|---|
| El conteo del segmento es **exacto** | `estimatedTotalHits` == verdad de referencia en 27 consultas × 7 escalas × 4 variantes (**189/189**) |
| Contar es barato, **extraer no** | filtrar 705,801 clientes: **5.0 ms**; faceter los 4M: **11.3 ms** |
| El tope de fábrica **trunca en silencio** | `limit=5000` → HTTP 200 con **1,000** hits; `offset=1000` → HTTP 200 con **0** hits |
| La paginación profunda explota | offset 0: **1.3 ms** → offset 1,000,000: **37–60 s** a 4M |
| El indexado se degrada con el volumen | 10,497 docs/s @100k → **284 docs/s** @4M (30.02 GiB de índice, 3.9 h) |
| Las consultas geo son la excepción | `_geoRadius` 25 km: 3.8 ms @1k → **140 ms** @4M |
| Concurrencia | 199 qps (1 cliente) → **1,582 qps** (32, saturación) → 0 errores |

Reporte completo: [`reports/REPORTE.md`](reports/REPORTE.md) ·
versión HTML autónoma: [`reports/index.html`](reports/index.html) ·
crudos: [`raw/`](raw) · tablas: [`reports/tables/`](reports/tables) ·
gráficas: [`reports/charts/`](reports/charts).

## Estructura

```
gen/spec.py              tablas, pesos, catálogo de 27 consultas y escalas
gen/gen_arrays.py        arreglos numpy de 4M registros + gen/ground_truth.json
gen/write_ndjson.py      dataset a data/ndjson/*.jsonl (40 shards de 100k)
bench/common.py          arranque/paro del servidor, settings, cliente HTTP, muestreo RSS/CPU
bench/run_scale.py       una escala completa (carga → consultas → concurrencia → paginación)
bench/run_all.py         orquesta las 7 escalas
bench/verify_ndjson.py   reverifica la verdad de referencia releyendo el NDJSON
bench/cap_limits.py      semántica de pagination.maxTotalHits (5 variantes × 2 valores)
bench/keyset_vs_offset.py paginación por offset vs paginación por llave
bench/selfcheck.py       autochequeo de invariantes de toda la corrida
bench/report.py          reports/REPORTE.md + CSV + SVG
bench/report_html.py     reports/index.html (un solo archivo, sin recursos remotos)
data/sample/             muestra de 1,000 documentos comprimida (253 KiB)
raw/                     resultados crudos por escala y experimentos (JSON)
reports/                 reporte, HTML, tablas CSV y gráficas SVG
```

No se versionan `bin/` (binario del motor), `data/arrays/`, `data/db/` ni `data/ndjson/`
(≈47 GiB): todo eso se regenera con los scripts de abajo.

## Requisitos

- Linux x86_64, Python ≥ 3.11 con `numpy`, `requests`, `urllib3`.
- ~6 GiB de disco para el NDJSON y ~45 GiB para las bases de todas las escalas (sólo hacen falta
  si se corre todo; con una escala basta su parte).
- RAM: la corrida usó `--max-indexing-memory 4GiB` en un host de 13 GiB.

Descarga del motor (checksum verificado):

```bash
mkdir -p bin && curl -sL -o bin/meilisearch \
  https://github.com/meilisearch/meilisearch/releases/download/v1.55.0/meilisearch-linux-amd64
chmod +x bin/meilisearch
sha256sum bin/meilisearch   # 7e33f5889235f14290074a19a6d3574bd9b10fb2ee8731eabb7dafd0714b0513
```

## Reproducción

```bash
python3 gen/gen_arrays.py            # arreglos + verdad de referencia (≈10 s)
python3 gen/write_ndjson.py --procs 10   # 4,000,000 de documentos en 40 shards (≈30 s)
python3 bench/verify_ndjson.py --procs 10 # relectura independiente: 108/108

python3 bench/run_scale.py --scale 1000000 --reps 20   # una escala concreta
python3 bench/run_all.py --reps 20 --batch 20000       # las 7 escalas

python3 bench/cap_limits.py --scale 4000000            # semántica del tope
python3 bench/keyset_vs_offset.py                      # offset vs keyset
python3 bench/selfcheck.py                             # invariantes: TODO OK
python3 bench/report.py && python3 bench/report_html.py
```

Etapas de `run_scale.py` (`--stages`):

| Etapa | Qué mide |
|---|---|
| `load` | índice, settings, indexado por lotes de 20k, docs/s, disco, RSS y CPU |
| `queries_default` | catálogo completo con `maxTotalHits=1000`, con `limit=20` y con `limit=1000` |
| `concurrency` | 1, 8, 32 y 64 clientes sobre una mezcla de consultas |
| `raise_cap` | costo de subir `pagination.maxTotalHits` |
| `queries_raised` | mismas consultas sin el techo |
| `verify_ids` | ids devueltos vs verdad de referencia |
| `typo_experiment` | efecto de `typoTolerance` en los conteos de texto |
| `deep` | paginación profunda con `sort=id:asc`, offsets 0 → 1,000,000 |

## Escalas y dataset

`1000 · 3000 · 10000 · 100000 · 300000 · 1000000 · 4000000`

Cada escala es el **prefijo determinista** del dataset (documentos `id 1..N`), por lo que los
conteos esperados de una escala son el conteo del prefijo: los resultados son comparables entre
escalas. 51 campos por documento, ≈1.3 KB de JSON (4.98 GiB de NDJSON en total) con identidad
(nombre, CURP, RFC, email, teléfono, `_geo`), ubicación (32 estados con pesos poblacionales),
crédito (score de buró correlacionado con banda de riesgo, monto, plazo, saldo, atraso), perfil
(KYC, estatus, canal, dispositivo, segmento) y tiempos.

## Verdad de referencia

`gen/ground_truth.json` contiene, por escala: el conteo exacto de las 27 consultas, la
distribución de facetas de las consultas de agregación, los 5 primeros `id` de cada segmento y el
perfil marginal de 12 campos categóricos. Se calcula con numpy y se revalida releyendo el NDJSON
con predicados independientes (`bench/verify_ndjson.py`): 108/108 comparaciones idénticas.

## Nota metodológica

- Las latencias de consulta se miden con un cliente HTTP mínimo (urllib3, keep-alive, sin
  reintentos). `requests.Session` —el cliente del SDK oficial de Python— añadía **~44 ms
  constantes por petición** en este host por una interacción Nagle/ACK diferido en loopback; la
  etapa `overhead_cliente` lo cuantifica en cada escala y queda en `raw/scale_<N>.json`.
- Se guarda en paralelo el `processingTimeMs` del motor para separar tiempo de servidor de tiempo
  de cliente.
- La base del laboratorio corre con `typoTolerance.enabled=false` para que los conteos de texto
  sean comparables 1:1 con la verdad de referencia; el experimento `typo_experiment` mide qué
  cambia al activarla.
- La escala de 4M se corrió con el motor como proceso nativo (`--env production`), no en
  contenedor: el host no tenía daemon de Docker ni sudo sin contraseña. Es el mismo binario oficial.

## Licencia

[MIT](LICENSE). Los datos son ficticios y generados por software con semilla fija.
