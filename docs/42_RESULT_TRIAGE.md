# 42 — Result triage: from a pile of verdicts to a report

> **What this is.** `bundle triage <run>` reduces a finished campaign's failures to the few
> distinct things that actually went wrong, attaches the smallest candidate that still shows each
> one, and ranks the axes whose values explain them. It reads only what the run already persisted
> and re-executes nothing.
>
> CLI summary: [04_CLI_AND_LIFECYCLE_REFERENCE.md](04_CLI_AND_LIFECYCLE_REFERENCE.md).
> Where the verdicts come from: [09_READER_EXECUTOR_AND_RESULTS.md](09_READER_EXECUTOR_AND_RESULTS.md).

---

## 1. The problem it exists for

A campaign is a measuring instrument, and a large one produces a lot of readings. What it does
*not* produce is a report.

Measured on this repository's own study material:

| campaign | candidates | failing | distinct causes |
|---|---|---|---|
| `proof_billing/c3_repeat` | 768 | 312 | **6** |
| `proof_fulfilment/d3_masked` | 2,048 | 572 | **1** |
| `proof_billing/c5_flagship` | 6,912 | 2,304 | 1 dominant |

Six things went wrong in the first run. The Executor reported three hundred and twelve failures.
Until something collapses the second number into the first, a green/red count is all you have, and
the work of finding out *what* broke is done by hand — which is how a genuinely rare defect gets
lost. In `c3_repeat` one of the six findings is carried by **three candidates out of 768**. It is
also one of the most interesting, and nothing about a list of 312 failures makes it visible.

Triage exists to make that reduction mechanical.

## 2. What it produces

```bash
python3 bundle_run.py triage /tmp/fw_work/mydb --write
```

```
triage 20260829T174918Z-67dc7ab3
  candidates 768   failing 312   distinct findings 6
  outcomes   DOMAIN_FAIL=312  PASS=456

FINDINGS  (one row per distinct failure, most frequent first)
  1. app=c3 inv=I8 trans=none                         136 candidates   43.6%
     minimal witness  225_0_0.py  (959B)
     app=c3  viol=1  inv=I8  trans=none  pror=credit  trace=refund>tick30>refund>up  cash=0
  ...
  6. app=c3 inv=I5 trans=none                           3 candidates    1.0%
     minimal witness  518_0_0.py  (995B)
     app=c3  viol=1  inv=I5  trans=none  pror=none  trace=coupon>tick30>coupon>tick30  couponlines=2

AXIS ENRICHMENT  (lift = how much this value changes the odds of failing; 1.0 = noise.
                  Ranked by how much of the corpus the effect explains.)
  pror           credit                    198/256     77.3%  lift  1.90  covers 33.3%
  cash           -1000                      87/87     100.0%  lift  2.46  covers 11.3%
  pror           immediate                  57/256     22.3%  lift  0.55  covers 33.3%
```

Three things, each answering a different question:

**Findings — *what* went wrong.** Failures grouped by what distinguishes them, so one defect is one
row however many candidates carry it. Rare findings keep their own row: finding 6 above is the
three-in-768 case.

**A minimal witness — *where to start*.** The smallest candidate that still exhibits the finding,
named by its source file so it can be opened directly. "Smallest" is source bytes: the Reader
assembles a candidate by concatenating the chosen slot values, so a shorter candidate is one that
selected shorter fragments and fewer optional pieces. It is a proxy for "simplest reproduction",
not a delta-debugged minimum.

**Axis enrichment — *why*.** For each declared value, how often it fails and the `lift` over the
run's base rate: `P(fail | value) / P(fail)`. A combinatorial design is balanced, so every value
appears in about the same number of candidates and lift is exactly the factor by which choosing
that value changes the odds of failing. `1.0` is noise; `pror=credit` at `1.90` is where to look.

## 3. How grouping decides what counts as "the same failure"

This needs no per-spec configuration, no naming convention, and no list of "error keys".

> A key whose value **never varies among the passing candidates** describes an outcome.
> A key that varies among them is an input axis the design was balancing.

`inv` is `none` on every passing candidate, so it says what went wrong. `pror` takes all three of
its values on passing candidates, so it says under what conditions. The signature of a failure is
its outcome keys; everything else becomes witness detail and enrichment input.

Two refinements came from running this on real campaigns rather than reasoning about it, and both
are asserted by tests so they stay fixed:

**A per-candidate detail is not an axis.** An operation trace takes a new value almost every time.
Each of its values then shows 100% failure on a support of one or two candidates, and those rows
outrank the config axis that actually explains the run. Keys above 24 distinct values are treated
as witness detail and excluded from enrichment; rows below 1% of the corpus are dropped; and
ranking is by how much of the corpus an effect explains — `|lift − 1| × coverage` — rather than by
effect size alone. Without that last part `cash=-1000` (11% of the corpus) outranks `pror=credit`
(33%).

**A measurement is not a category.** A balance or a shipment count is constant across the passing
candidates — the clean run always lands on the same number — so the passing-set rule alone reads it
as part of a failure's identity. It is not. On `d3_masked` this fractured **one** defect into four
findings that differed only in how much money was lost. Keys whose every observed value parses as a
number are measurements: they stay out of the signature and remain on the witness.

**A key that restates the verdict explains nothing.** A violation *count* is non-zero exactly when
the candidate failed, so all of its values sit at 0% or 100%. Reporting that as the strongest signal
in the run is true and useless, and it displaces the axis that does explain something. Keys that
partition exactly along the pass/fail boundary are excluded from enrichment.

### A limitation, stated rather than hidden

An axis that predicts the outcome **perfectly** is also constant among the passing candidates, so it
is read as part of the failure's identity rather than as enrichment. Nothing is lost — it appears in
the finding's label, which is where a reader looks first — but it carries no lift number. There is a
test asserting this so it stays a known property rather than becoming a surprise.

## 4. What it reads, and what it refuses to do

Its input is the Executor's own K=V corpus, `metrics.kv`, plus `executor-summary.json` for the
outcome totals.

**It never re-executes a candidate.** Re-running generated code outside the run's recorded execution
policy would bypass the sandbox, and a stateful candidate — one whose `FW_Optional` sudden action
rotated a key or poisoned a cache — produces a different, wrong verdict on a second firing. The
Executor makes exactly this argument where it harvests metrics, and triage inherits it. Like
`report`, it is therefore safe to point at a failed, cancelled or interrupted run, which is usually
when you most want it.

### The one thing a spec must do

A candidate contributes a metrics line **only** when it prints one starting with `app=` and
containing `FW_VAR=`. That is the Executor's documented selection rule, the same one `collect_kv`
uses. A `TAIL` slot like this participates:

```python
print("app=c3 viol=%d inv=%s pror=%s FW_VAR=%d" % (len(_bad), "+".join(_bad) or "none", _pror, FW_VAR))
```

and one printing the same fields *without* the `app=` prefix does not — every line is skipped,
`metrics.kv` comes out empty, and both the Analyzer and triage have nothing to read. This is easy
to get wrong and silent when you do: the run is green, the stage reports success, and the corpus is
empty. Triage says so explicitly rather than reporting "no findings" over no data:

```
! no K=V corpus: metrics.kv is absent or empty, so failures cannot be grouped.
  A candidate contributes a line only when it prints one starting with 'app=' and
  containing 'FW_VAR=' -- check the spec's TAIL slot against that rule.
```

## 5. The JSON contract

`--write` puts `triage.json` in the run directory; `--json PATH` writes it anywhere. Schema
`bundle.triage/v1`:

```jsonc
{
  "schema": "bundle.triage/v1",
  "run_id": "20260829T174918Z-67dc7ab3",
  "corpus":  { "path": "…/metrics.kv", "records": 768, "failing": 312,
               "processed": 768, "outcomes": { "PASS": 456, "DOMAIN_FAIL": 312, … } },
  "keys":    { "classifying": ["app","inv","trans"],        // what went wrong
               "descriptive": ["cash","couponlines","pror","trace","viol"] },  // under what conditions
  "findings": [
    { "signature": [["app","c3"],["inv","I8"],["trans","none"]],
      "label": "app=c3 inv=I8 trans=none",
      "count": 136, "share": 0.4359,
      "witness": { "candidate_id": "225_0_0", "source_ref": "225_0_0.py",
                   "source_bytes": 959, "detail": { "inv": "I8", "pror": "credit", … } } }
  ],
  "enrichment": [
    { "key": "pror", "value": "credit", "failing": 198, "total": 256,
      "rate": 0.7734, "lift": 1.904, "coverage": 0.3333, "score": 0.3013 }
  ],
  "notes": []
}
```

`notes` carries anything the reader must not miss — an empty corpus, or a run whose failures share
one undifferentiated signature.

## 6. Options

| flag | effect |
|---|---|
| *(none)* | print the report; write nothing |
| `--write` | also write `triage.json` into the run directory |
| `--json PATH` | write the report JSON to `PATH` |
| `--top N` | how many enrichment rows to show (default 12; `0` hides the section) |
| `--fail-on-findings` | exit non-zero when the run produced any finding — for CI |

`RUN` may be a run directory, or any path containing `runs/<run-id>/`, in which case the most recent
run is taken. `bundle triage /tmp/fw_work/mydb` therefore does what you mean.

## 7. How to read a result

- **One finding covering everything** usually means the campaign is *saturated*: a single dominant
  defect is firing on most candidates and hiding the rest. That is normal on a first run. Mask the
  explained shape — with a sieve bond ([07_CONSTRAINTS_GUIDE.md](07_CONSTRAINTS_GUIDE.md)) or a
  config flag — and run again; the residue is the next finding.
- **A finding with a very small count** is the one to read first, not last. It is the case the
  design reached and nothing else would have.
- **Lift near 1.0 everywhere** means no single axis explains the failures; the cause is an
  interaction, and the finding labels and witnesses will tell you more than the enrichment table.
- **Enrichment empty but findings present** means every reported key was either witness detail or a
  restatement of the verdict — look at the witnesses.
