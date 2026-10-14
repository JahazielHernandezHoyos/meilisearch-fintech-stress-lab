"""Utilidades comunes del laboratorio: arranque/paro del servidor Meilisearch,
cliente HTTP, settings, muestreo de RSS y espera de tareas."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gen"))
import spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "meilisearch"
NDJSON = ROOT / "data" / "ndjson"
RAW = ROOT / "raw"
LOGS = ROOT / "logs"
KEY = "fintech-lab-master-key"

FILTERABLE = ["estado", "municipio", "producto", "kyc_status", "estatus_cuenta",
              "canal_adquisicion", "dispositivo", "banda_riesgo", "banda_ingreso",
              "tipo_vivienda", "nivel_educativo", "tipo_contrato",
              "segmento_comercial", "genero", "acepta_marketing", "tiene_seguro",
              "tags", "score_buro", "edad", "dias_atraso", "monto_solicitado",
              "ingreso_mensual", "num_prestamos", "saldo_actual", "cp",
              "fecha_registro_ts", "fecha_ultimo_acceso_ts", "limite_credito",
              "credito_usado", "utilizacion_pct", "score_interno", "_geo"]
SORTABLE = ["id", "score_buro", "ingreso_mensual", "edad", "fecha_registro_ts",
            "monto_solicitado", "saldo_actual", "dias_atraso", "num_prestamos",
            "limite_credito", "utilizacion_pct"]
SEARCHABLE = ["nombre", "apellido_paterno", "apellido_materno", "nombre_completo",
              "colonia", "municipio", "curp", "rfc", "email", "telefono", "tags"]


def settings(max_total_hits: int, typos: bool = False) -> dict:
    """Settings del indice.

    `typos=False` por defecto: los conteos de las consultas de texto deben ser
    comparables 1:1 contra el ground truth (token exacto). El experimento de
    tolerancia a erratas levanta esta bandera a proposito.
    """
    return {
        "searchableAttributes": SEARCHABLE,
        "filterableAttributes": FILTERABLE,
        "sortableAttributes": SORTABLE,
        "displayedAttributes": ["*"],
        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
        "pagination": {"maxTotalHits": max_total_hits},
        "typoTolerance": {"enabled": typos,
                          "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9}},
        "faceting": {"maxValuesPerFacet": 100},
    }


class Meili:
    """Servidor Meilisearch local (proceso hijo) + cliente HTTP."""

    def __init__(self, db_path: Path, port: int = 7700, threads: int = 8,
                 memory: str = "4GiB", max_total_hits: int = 1000, label: str = "run"):
        self.db_path = Path(db_path)
        self.port = port
        self.threads = threads
        self.memory = memory
        self.max_total_hits = max_total_hits
        self.label = label
        self.proc: subprocess.Popen | None = None
        self.rss_samples: list = []
        self.cpu_samples: list = []
        self._stop = threading.Event()
        self.base = f"http://127.0.0.1:{port}"
        self.http = requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {KEY}",
                                  "Content-Type": "application/json"})
        self.fast = FastHttp(self.base, KEY)

    # ---------------------------------------------------------------- server
    def start(self):
        self.db_path.mkdir(parents=True, exist_ok=True)
        LOGS.mkdir(exist_ok=True)
        self.log_path = LOGS / f"meili_{self.label}.log"
        self._logfh = open(self.log_path, "w")
        cmd = [str(BIN),
               "--db-path", str(self.db_path),
               "--http-addr", f"127.0.0.1:{self.port}",
               "--master-key", KEY,
               "--env", "production",
               "--max-indexing-threads", str(self.threads),
               "--max-indexing-memory", self.memory,
               "--log-level", "WARN",
               "--no-analytics"]
        t0 = time.time()
        self.proc = subprocess.Popen(cmd, stdout=self._logfh, stderr=subprocess.STDOUT)
        self.ready_s = None
        while time.time() - t0 < 120:
            try:
                r = requests.get(f"{self.base}/health", timeout=1)
                if r.status_code == 200:
                    self.ready_s = time.time() - t0
                    break
            except requests.RequestException:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(f"meilisearch murio al arrancar; ver {self.log_path}")
            time.sleep(0.2)
        if self.ready_s is None:
            raise RuntimeError("timeout esperando /health")
        self._stop.clear()
        self._sampler = threading.Thread(target=self._sample_rss, daemon=True)
        self._sampler.start()
        return self.ready_s

    def _sample_rss(self):
        status = Path(f"/proc/{self.proc.pid}/status")
        stat = Path(f"/proc/{self.proc.pid}/stat")
        hz = os.sysconf("SC_CLK_TCK")
        prev = None
        while not self._stop.wait(0.5):
            try:
                txt = status.read_text()
                m = re.search(r"VmRSS:\s+(\d+) kB", txt)
                if m:
                    self.rss_samples.append((round(time.time(), 2), int(m.group(1)) * 1024))
                st = stat.read_text().rsplit(")", 1)[1].split()
                ticks = int(st[11]) + int(st[12])  # utime + stime
                now = time.time()
                if prev is not None:
                    dt = now - prev[1]
                    if dt > 0:
                        self.cpu_samples.append((round(now, 2), (ticks - prev[0]) / hz / dt * 100.0))
                prev = (ticks, now)
            except (OSError, IndexError):
                return

    def peak_rss(self):
        return max((v for _, v in self.rss_samples), default=0)

    def cpu_stats(self):
        if not self.cpu_samples:
            return {}
        vals = [v for _, v in self.cpu_samples]
        return {"cpu_pct_max": round(max(vals), 1),
                "cpu_pct_p50": round(pct(vals, 50), 1),
                "cpu_pct_mean": round(sum(vals) / len(vals), 1)}

    def mark(self) -> int:
        return len(self.rss_samples)

    def peak_rss_since(self, mark: int) -> int:
        return max((v for _, v in self.rss_samples[mark:]), default=0)

    def cpu_since(self, mark: int) -> dict:
        vals = [v for _, v in self.cpu_samples[mark:]]
        if not vals:
            return {}
        return {"cpu_pct_max": round(max(vals), 1),
                "cpu_pct_p50": round(pct(vals, 50), 1),
                "cpu_pct_mean": round(sum(vals) / len(vals), 1)}

    def stop(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        try:
            self._logfh.close()
        except Exception:
            pass

    # ---------------------------------------------------------------- tareas
    def wait_task(self, uid: int, timeout: float = 3600) -> dict:
        t0 = time.time()
        while True:
            r = self.http.get(f"{self.base}/tasks/{uid}", timeout=30)
            r.raise_for_status()
            t = r.json()
            if t["status"] in ("succeeded", "failed", "canceled"):
                return t
            if time.time() - t0 > timeout:
                raise TimeoutError(f"task {uid} no termino en {timeout}s")
            time.sleep(0.05)

    def create_index(self, uid: str):
        r = self.http.post(f"{self.base}/indexes", json={"uid": uid, "primaryKey": "id"})
        if r.status_code not in (200, 202):
            raise RuntimeError(f"create_index: {r.status_code} {r.text[:200]}")
        return self.wait_task(r.json()["taskUid"])

    def apply_settings(self, uid: str) -> float:
        t0 = time.time()
        r = self.http.patch(f"{self.base}/indexes/{uid}/settings", json=settings(self.max_total_hits))
        r.raise_for_status()
        t = self.wait_task(r.json()["taskUid"])
        if t["status"] != "succeeded":
            raise RuntimeError(f"settings fallaron: {t}")
        return time.time() - t0

    def index_stats(self, uid: str) -> dict:
        r = self.http.get(f"{self.base}/indexes/{uid}/stats", timeout=60)
        r.raise_for_status()
        return r.json()

    def db_size_bytes(self) -> int:
        total = 0
        for root, _dirs, files in os.walk(self.db_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total


class FastHttp:
    """Cliente HTTP de baja sobrecarga para medir latencia real del motor.

    urllib3 con keep-alive y sin reintentos; requests.Session resulto anadir
    ~45 ms constantes por POST /search en este host (interaccion
    Nagle/ACK-diferido con loopback), lo que enmascararia la senal medida.
    """

    def __init__(self, base: str, key: str = KEY, maxsize: int = 128):
        import urllib3
        self._urllib3 = urllib3
        self.base = base
        self.key = key
        self.pool = urllib3.PoolManager(maxsize=maxsize, block=False, retries=False)

    def search(self, uid: str, body: dict, timeout: float = 600):
        """POST /indexes/<uid>/search. Devuelve (status, json|None, wall_ms, bytes)."""
        import json as _json
        payload = _json.dumps(body, separators=(",", ":")).encode()
        t0 = time.perf_counter()
        r = self.pool.request("POST", f"{self.base}/indexes/{uid}/search", body=payload,
                              headers={"Content-Type": "application/json",
                                       "Authorization": f"Bearer {self.key}"},
                              timeout=self._urllib3.Timeout(connect=5, read=timeout),
                              preload_content=True)
        data = r.data
        wall = (time.perf_counter() - t0) * 1000
        try:
            j = _json.loads(data)
        except Exception:
            j = None
        return r.status, j, wall, len(data)


def iter_docs(limit: int):
    emitted = 0
    for shard in range((spec.TOTAL + spec.SHARD_SIZE - 1) // spec.SHARD_SIZE):
        if emitted >= limit:
            return
        p = NDJSON / f"part-{shard:05d}.jsonl"
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                if emitted >= limit:
                    return
                emitted += 1
                yield line


def batches(limit: int, batch: int):
    buf = []
    n = 0
    for line in iter_docs(limit):
        buf.append(line)
        if len(buf) >= batch:
            yield buf
            n += len(buf)
            buf = []
    if buf:
        yield buf


def sysinfo() -> dict:
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        mem[k] = v.strip()
    return {
        "cpu_model": [l.strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                      if l.startswith("model name")][0].split(":")[1].strip(),
        "nproc": os.cpu_count(),
        "mem_total_kb": int(mem["MemTotal"].split()[0]),
        "kernel": os.uname().release,
    }


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
