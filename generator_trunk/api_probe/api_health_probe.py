#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

# =============================================================================
# api_health_probe  —  metrics-rich data-quality probe over a SAFE public API
# =============================================================================
# WHAT IT DOES
#   Pulls a numeric time-series (hourly 2 m air temperature) from a reputable,
#   free, no-auth, READ-ONLY public API (Open-Meteo), measures a battery of
#   statistical + data-quality metrics over the returned data, persists the
#   processed summary into a LOCAL PostgreSQL database, and emits a single
#   aggregated K=V metrics line on stdout. It is self-checking: FW_VAR=1 iff a
#   data-integrity invariant is violated, else FW_VAR=0.
#
#   This is the "seed" program for the Combinatorics Bundle: it is decomposed
#   into logical pieces, each piece rewritten several ways, and the rewrites are
#   combined by the Core so the engine breeds — and scores — variations.
#
# -----------------------------------------------------------------------------
# SECURITY CONTRACT  (inbound-only; the API can neither read, alter nor delete
# any local data — addressing the operator's explicit constraints):
#   * READ-ONLY GET to https://api.open-meteo.com — a well-established, free,
#     keyless weather provider. The request carries ONLY public coordinates
#     (latitude/longitude) + a variable name. No credentials, no secrets, and
#     none of the operator's data ever leave this machine.
#   * The API is a DATA SOURCE, not a sink: its response flows IN, is parsed and
#     measured locally, and only LOCALLY-COMPUTED numbers are written to the DB.
#     The provider has zero access to PostgreSQL, the filesystem or any creds.
#   * SQL-INJECTION SAFE: every DB write is a PARAMETERIZED statement (values
#     bound via the driver, never string-formatted into SQL). Every API-derived
#     value is coerced to float/int BEFORE it can reach the DB layer; table and
#     database identifiers are local constants, never taken from the response.
#   * Least authority: writes go only into a FRESH database (apiweather_app)
#     this program creates; no pre-existing data is read or modified.
#   * Fail-safe: network or DB errors degrade gracefully (offline sample / db_ok
#     =false) so the program always completes and always prints its K=V line.
# =============================================================================

# ┌───────────────────────────────────────────────────────────────────────────
# │ METRICS HEADER  (K=V)  — every key this probe tracks. Static config values
# │ are fixed here; data-measurement keys start at sentinel and are filled while
# │ the API payload is processed. The tail aggregates ALL of them into one line.
# ├───────────────────────────────────────────────────────────────────────────
# │ app=api_health_probe          schema_ver=3            run_kind=seed
# │ api_provider=open-meteo        api_auth=none          api_access=read-only
# │ endpoint=/v1/forecast          http_method=GET        transport=https
# │ latitude=52.5200               longitude=13.4050      hourly_var=temperature_2m
# │ forecast_days=2                timezone=UTC           http_timeout_s=8.0
# │ db_host=127.0.0.1              db_port=5433           db_name=apiweather_app
# │ outlier_clip=p05_p95           tol_abs=1e-6           score_lo=-50 score_hi=80
# │ --- measured from the API data (filled at runtime) ---
# │ http_status=?   latency_ms=?   bytes_in=?    source=?
# │ rows=?          nulls=?        distinct_hours=?        coverage=?
# │ t_min=?  t_max=? t_mean=?  t_median=?  t_stdev=?  t_var=?  t_range=?
# │ t_p05=?  t_p95=? t_iqr=?   t_sum=?     monotonic_breaks=?  zero_crossings=?
# │ score=?  dq_score=?  violations=?      sum_ok=? count_ok=? range_ok=?
# │ db_ms=?  rows_written=?  bucket_sum=?  db_ok=?    FW_VAR=?
# └───────────────────────────────────────────────────────────────────────────

import json
import math
import os
import socket
import statistics
import time
import urllib.parse
import urllib.request

# ----------------------------- configuration -------------------------------- #
SCHEMA_VER     = 3
API_BASE       = "https://api.open-meteo.com/v1/forecast"
LATITUDE       = 52.5200          # Berlin — a public coordinate, nothing personal
LONGITUDE      = 13.4050
HOURLY_VAR     = "temperature_2m"
FORECAST_DAYS  = 2
TIMEZONE       = "UTC"
HTTP_TIMEOUT_S = 8.0
CACHE_PATH     = os.path.join(os.environ.get("TMPDIR", "/tmp"), "api_health_probe.cache.json")

DB_HOST, DB_PORT = "127.0.0.1", 5433
DB_NAME          = "apiweather_app"            # a FRESH db this program owns
DB_USER, DB_PASS = "postgres", "pass"

TOL_ABS          = 1e-6
SCORE_LO, SCORE_HI = -50.0, 80.0               # health-score sanity window
RUN_ID           = int(time.time())
COMBO_ID         = os.environ.get("FW_COMBO_ID", "seed")

# Deterministic offline fallback (used only if the network is unavailable, so the
# probe still completes). 12 plausible hourly °C readings.
OFFLINE_SAMPLE = {"hourly": {"time": [f"2026-05-31T{h:02d}:00" for h in range(12)],
                             "temperature_2m": [9.3, 8.7, 8.1, 7.9, 8.4, 10.2,
                                                12.8, 15.1, 17.6, 19.0, 19.8, 19.4]}}

# The running metrics dict — the "K=V header" made live.
METRICS = {
    "app": "api_health_probe", "schema_ver": SCHEMA_VER, "run_id": RUN_ID,
    "combo_id": COMBO_ID, "api_provider": "open-meteo", "hourly_var": HOURLY_VAR,
    "http_status": 0, "latency_ms": 0, "bytes_in": 0, "source": "none",
    "rows": 0, "nulls": 0, "distinct_hours": 0, "coverage": 0.0,
    "t_min": float("nan"), "t_max": float("nan"), "t_mean": float("nan"),
    "t_median": float("nan"), "t_stdev": float("nan"), "t_var": float("nan"),
    "t_range": float("nan"), "t_p05": float("nan"), "t_p95": float("nan"),
    "t_iqr": float("nan"), "t_sum": float("nan"),
    "monotonic_breaks": 0, "zero_crossings": 0,
    "score": float("nan"), "dq_score": 0.0, "violations": 0,
    "sum_ok": 1, "count_ok": 1, "range_ok": 1,
    "db_ms": 0, "rows_written": 0, "bucket_sum": 0, "db_ok": 0, "FW_VAR": 0,
}


# -------------------------------- helpers ----------------------------------- #
def now_ms():
    return time.monotonic() * 1000.0


def pctl(sorted_vals, q):
    """Linear-interpolation percentile (q in [0,1]) over an already-sorted list."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(sorted_vals[hi]) * frac


def http_get_json_cached(url, timeout):
    """Inbound-only READ. Returns (obj, http_status, source). Caches the raw body
    to a temp file so repeated runs make at most one real network call; falls
    back to the deterministic offline sample on ANY error (never raises)."""
    if os.path.isfile(CACHE_PATH):
        try:
            body = open(CACHE_PATH, "rb").read()
            return json.loads(body.decode("utf-8")), 200, "cache"
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "api-health-probe/3"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.getcode()
        try:
            with open(CACHE_PATH, "wb") as fh:
                fh.write(body)
        except Exception:
            pass
        return json.loads(body.decode("utf-8")), status, "live"
    except Exception:
        return OFFLINE_SAMPLE, 0, "offline"


def db_connect(dbname):
    import pg8000.dbapi
    return pg8000.dbapi.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                                password=DB_PASS, database=dbname, timeout=8)


def ensure_app_db():
    """Create the FRESH app database if it does not exist (no existing db touched)."""
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                                    password=DB_PASS, database="postgres", timeout=8)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')   # identifier is a local constant
        cur.close()
        conn.close()
        return True
    except Exception:
        return False


def persist(metrics, histogram):
    """Write the processed summary + histogram to local PG via PARAMETERIZED SQL.
    Returns (rows_written, db_ok, db_ms, bucket_sum). API values never reach SQL
    as text — they are bound parameters, already coerced to float/int upstream."""
    t0 = now_ms()
    rows_written, bucket_sum = 0, 0
    try:
        conn = db_connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS probe_metrics (
                id            bigserial PRIMARY KEY,
                run_id        bigint,  combo_id text,  source text,
                rows          integer, nulls    integer,
                t_mean double precision, t_stdev double precision,
                t_min  double precision, t_max   double precision,
                t_range double precision, t_sum  double precision,
                score  double precision, dq_score double precision,
                latency_ms double precision, fw_var integer,
                created_at timestamptz DEFAULT now())""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS probe_histogram (
                run_id bigint, combo_id text, bucket integer, cnt integer)""")
        # parameterized INSERT — every %s is a bound value, never interpolated
        cur.execute("""
            INSERT INTO probe_metrics (run_id, combo_id, source, rows, nulls,
                t_mean, t_stdev, t_min, t_max, t_range, t_sum, score, dq_score,
                latency_ms, fw_var)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (int(metrics["run_id"]), str(metrics["combo_id"]), str(metrics["source"]),
             int(metrics["rows"]), int(metrics["nulls"]),
             float(metrics["t_mean"]), float(metrics["t_stdev"]),
             float(metrics["t_min"]), float(metrics["t_max"]),
             float(metrics["t_range"]), float(metrics["t_sum"]),
             float(metrics["score"]), float(metrics["dq_score"]),
             float(metrics["latency_ms"]), int(metrics["FW_VAR"])))
        rows_written += 1
        for bucket, cnt in histogram:
            cur.execute("INSERT INTO probe_histogram (run_id, combo_id, bucket, cnt) "
                        "VALUES (%s,%s,%s,%s)",
                        (int(metrics["run_id"]), str(metrics["combo_id"]),
                         int(bucket), int(cnt)))
            bucket_sum += int(cnt)
        conn.commit()
        cur.close()
        conn.close()
        return rows_written, 1, now_ms() - t0, bucket_sum
    except Exception:
        return 0, 0, now_ms() - t0, 0


def histogram_of(values, nbins=8):
    """Equal-width histogram → list[(bucket_index, count)]."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    counts = [0] * nbins
    for v in values:
        idx = min(nbins - 1, int((v - lo) / span * nbins))
        counts[idx] += 1
    return list(enumerate(counts))


# ---------------------------------- main ------------------------------------ #
def main():
    # --- FETCH (inbound-only, read-only) ---
    qs = urllib.parse.urlencode({"latitude": LATITUDE, "longitude": LONGITUDE,
                                 "hourly": HOURLY_VAR, "forecast_days": FORECAST_DAYS,
                                 "timezone": TIMEZONE})
    url = f"{API_BASE}?{qs}"
    t0 = now_ms()
    payload, status, source = http_get_json_cached(url, HTTP_TIMEOUT_S)
    METRICS["latency_ms"] = round(now_ms() - t0, 3)
    METRICS["http_status"] = int(status)
    METRICS["source"] = source
    METRICS["bytes_in"] = len(json.dumps(payload).encode("utf-8"))

    # --- PARSE (coerce every API number to float; drop non-numeric) ---
    hourly = payload.get("hourly", {}) if isinstance(payload, dict) else {}
    raw_temps = hourly.get(HOURLY_VAR, []) or []
    raw_hours = hourly.get("time", []) or []
    temps, nulls = [], 0
    for v in raw_temps:
        try:
            f = float(v)
            if f == f and not math.isinf(f):       # reject NaN/inf
                temps.append(f)
            else:
                nulls += 1
        except (TypeError, ValueError):
            nulls += 1
    METRICS["rows"] = len(temps)
    METRICS["nulls"] = nulls
    METRICS["distinct_hours"] = len(set(raw_hours))
    METRICS["coverage"] = round(len(temps) / (len(raw_temps) or 1), 4)

    # --- CLEAN (optional refinement: clip outliers to the [p05,p95] band) ---
    if temps:
        s = sorted(temps)
        p05, p95 = pctl(s, 0.05), pctl(s, 0.95)
        temps = [min(max(t, p05), p95) for t in temps]

    # --- AGGREGATE ---
    if temps:
        s = sorted(temps)
        METRICS["t_min"] = float(s[0])
        METRICS["t_max"] = float(s[-1])
        METRICS["t_sum"] = float(sum(temps))
        METRICS["t_mean"] = statistics.fmean(temps)
        METRICS["t_median"] = statistics.median(temps)
        METRICS["t_stdev"] = statistics.pstdev(temps)
        METRICS["t_var"] = statistics.pvariance(temps)
        METRICS["t_range"] = METRICS["t_max"] - METRICS["t_min"]
        METRICS["t_p05"] = pctl(s, 0.05)
        METRICS["t_p95"] = pctl(s, 0.95)
        METRICS["t_iqr"] = pctl(s, 0.75) - pctl(s, 0.25)
        METRICS["monotonic_breaks"] = sum(1 for i in range(1, len(temps))
                                          if temps[i] < temps[i - 1])
        mean = METRICS["t_mean"]
        METRICS["zero_crossings"] = sum(1 for i in range(1, len(temps))
                                        if (temps[i] - mean) * (temps[i - 1] - mean) < 0)

    # --- TRANSFORM (order-sensitive health score: offset → scale → clip) ---
    score = METRICS["t_mean"] if METRICS["t_mean"] == METRICS["t_mean"] else 0.0
    score = score - 10.0          # offset: baseline subtraction
    score = score * 1.5           # scale
    score = min(score, 25.0)      # clip
    METRICS["score"] = round(score, 4)

    # --- PERSIST (parameterized; local DB only) ---
    ensure_app_db()
    hist = histogram_of(temps)
    rw, db_ok, db_ms, bsum = persist(METRICS, hist)
    METRICS["rows_written"] = rw
    METRICS["db_ok"] = db_ok
    METRICS["db_ms"] = round(db_ms, 3)
    METRICS["bucket_sum"] = bsum

    # --- VERDICT (independent recompute = the in-program oracle) ---
    chk_sum = 0.0
    for t in temps:
        chk_sum += t
    sum_ok = abs(chk_sum - (METRICS["t_sum"] if METRICS["t_sum"] == METRICS["t_sum"]
                            else 0.0)) <= TOL_ABS * (1 + abs(chk_sum))
    count_ok = (METRICS["rows"] == len(temps))
    range_ok = (not temps) or (METRICS["t_max"] >= METRICS["t_min"]
               and abs(METRICS["t_range"] - (METRICS["t_max"] - METRICS["t_min"])) <= 1e-9)
    bucket_ok = (rw == 0) or (bsum == len(temps))
    score_ok = (SCORE_LO <= METRICS["score"] <= SCORE_HI)
    finite_ok = all(x == x for x in (METRICS["t_mean"], METRICS["t_stdev"],
                                     METRICS["t_median"], METRICS["score"]))
    checks = [sum_ok, count_ok, range_ok, bucket_ok, score_ok, finite_ok]
    METRICS["sum_ok"] = int(sum_ok)
    METRICS["count_ok"] = int(count_ok)
    METRICS["range_ok"] = int(range_ok)
    METRICS["violations"] = sum(1 for c in checks if not c)
    METRICS["dq_score"] = round(sum(1 for c in checks if c) / len(checks), 4)
    FW_VAR = 0 if all(checks) else 1
    METRICS["FW_VAR"] = FW_VAR

    # --- TAIL: aggregate ALL metrics into ONE K=V line on stdout ---
    line = " ".join(f"{k}={_fmt(v)}" for k, v in METRICS.items())
    print(line)
    return FW_VAR


def _fmt(v):
    if isinstance(v, float):
        if v != v:
            return "nan"
        return f"{v:.4f}".rstrip("0").rstrip(".") if v == v else "nan"
    return str(v)


if __name__ == "__main__":
    raise SystemExit(main())
