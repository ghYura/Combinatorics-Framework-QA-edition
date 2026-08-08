# First live-model run: the target model 3.5 the target model

**Date:** 2026-08-06 · **Target:** the target model `3.5 the target model` (web UI, one account) · **Requests:** 108,
zero transport errors, 29.3 min · **Cost:** no API billing (account quota)

Every number this platform had produced before this run came from a pipeline control. This is the
first measurement of a real target, and its most useful result is **methodological rather than a
score**: it shows that one of the three marginals must be measured before the other two mean
anything.

---

## 1. Test design

### 1.1 What is varied, and why exactly these axes

One task family (`ordering`) — the answer is exactly solvable, so every verdict is objective and no
LLM judge is in the loop. Three tasks, twelve presentations each, three repeats:

| Factor | Levels | Purpose |
| --- | --- | --- |
| task | seeds `20260806`, `777001`, `424242` at complexity **3, 4, 5** | multiple tasks *and* a capability ladder from one run |
| `schema` | `json`, `plain`, `csv` | output-serialization invariance |
| `long_range` | `0`, `3` | declared-neutral filler invariance |
| `constraint_order` | `forward`, `reverse` | constraint-listing invariance |
| **K (repeats)** | **3** | separates non-determinism from everything else |

`3 tasks × 12 presentations × 3 repeats = 108 requests.`

The three presentation axes are all **declared invariant**: none of them changes what the correct
answer is. That is what makes disagreement across them a defect rather than a difference, and it is
why `distractor=contradictory` and `paraphrase=inverted` are excluded from the relation set — they
are *designed* to interfere, so asserting invariance over them would manufacture violations that are
correct behaviour.

### 1.2 Two verdicts per response, deliberately kept apart

| Verdict | Ground truth? | Question |
| --- | --- | --- |
| **oracle** (`FW_VAR`) | yes | is this exactly right, and does it obey the output contract? |
| **orbit / metamorphic** | **no** | did every member of this equivalence class give the *same* answer? |

The second needs no expected answer at all, which is what lets the approach extend past exactly
solvable tasks. Both are reported because they disagree in informative ways.

### 1.3 Strict verdict, lenient comparison

The oracle stays strict: a response prefixed with `JSON\n` is a **format failure**, full stop.

But orbit comparison uses a *lenient* extraction of the same response. This is not a softening — it
was forced by a measured defect in the first K=1 run (§4.1): format-only failures collapsed to a
single `unparsed` digest, so two **substantively different** answers compared as "not comparable" and
a real invariance violation was reported as clean. Format compliance and semantic agreement are
different findings, and the stricter one must not erase the other.

### 1.4 Experimental hygiene

| Control | Implementation | Why it matters |
| --- | --- | --- |
| **independence** | fresh conversation per candidate | reusing a thread lets candidate *n* see *n−1*; the orbit would look consistent because the model was echoing itself |
| **no personalization** | the target model **temporary chat**, re-engaged per candidate | account history feeds personalization, so 108 sequential requests could otherwise condition the target |
| **model pinned** | picker set to the target model explicitly, verified, fails closed | a result that cannot name its model is not evidence |
| **profile isolation** | derived profile with session files only | the operator's real 4 GB profile is never opened for writing |

**Honest limitation on one of these.** Temporary chat was verified *by effect* in a dedicated probe —
history stayed at 31 conversations before and after sending a message. The in-run post-condition is
weaker: on the temporary-chat screen the sidebar reports `0`, so an "after ≤ before" check passes
trivially. The dedicated probe is the real evidence; the in-run check is not.

---

## 2. Headline results

```
ACCURACY     40/108 = 37.0%
verdicts     format-failure 58 · correct 40 · wrong-answer 10

CAPABILITY   complexity 3: 0.333   complexity 4: 0.472   complexity 5: 0.306
             ceiling = none in 3..5, and NOT monotonic

STABILITY    31 of 36 cells disagree across 3 identical repeats = 0.861
             answers per cell: 1 answer × 5 · 2 answers × 25 · 3 answers × 6

INVARIANCE   0.804 overall (constraint_order 0.67 · neutral_context 0.83 · schema 0.92)
FRAGILITY    0.944 of the presentation space
```

---

## 3. What these numbers do and do not support

### 3.1 The dominant failure is format, not reasoning

**58 of 108 (54%) are format failures; only 10 are wrong answers.** The model largely *knows* the
answer and does not obey the output contract — most often a `JSON` preamble before the JSON object.

This is precisely the split the decomposition exists to expose. One accuracy figure would have said
"37%", inviting "use a bigger model". The decomposition says: **fix the output contract first**, and
most of the gap closes without changing models.

### 3.2 Instability dominates — and it invalidates the other two readings

**31 of 36 cells returned different answers to three identical requests. Six cells produced three
distinct answers in three tries.**

This is the run's most important result, and it is a warning about interpretation:

> When instability is 0.86, fragility and invariance **cannot** be attributed to presentation.
> They are measuring the same non-determinism from a different angle.

The invariance figure of 0.804 must therefore **not** be read as "phrasing changes the answer 80% of
the time". Comparing per-cell *majority* answers instead shows only **3–4 distinct majority answers
per task across 12 presentations** — far less presentation sensitivity than the raw figure implies.

The methodological rule this establishes:

> **Stability must be measured first, because it bounds what every other measurement can mean.**
> At K=1 each cell has one sample, so instability is silently absorbed into "fragility" — the number
> is reported with confidence and means something else entirely.

### 3.3 The K=1 run was not representative — including my own earlier conclusion

| | K=1, 1 task, 12 requests | K=3, 3 tasks, 108 requests |
| --- | --- | --- |
| accuracy | 83.3% | **37.0%** |
| invariance | 0.235 | 0.804 (uninterpretable, see §3.2) |
| instability | **unmeasurable** | 0.861 |

The earlier run concluded there was "one real disagreement, isolated to `json + filler=0 + reverse`".
With K=3 that cell is unremarkable — it was a sample from a broadly non-deterministic distribution,
not a systematic weak spot. **That conclusion was wrong, and only K>1 could show it.**

### 3.4 No capability ceiling in this range

Pass rate by size is **0.333 / 0.472 / 0.306** for complexity 3/4/5 — non-monotonic, so task size is
not the driver here. The ceiling detector correctly reports `None` rather than inventing one: it
stops at the first level below threshold instead of reporting the last lucky success.

---

## 4. Engineering defects found while building this

Each was found by the run failing honestly rather than by inspection.

### 4.1 Format failures masked a real invariance violation
Two responses differing only in `constraint_order` gave **different answers**, but both carried a
`JSON\n` prefix, failed the strict parser, and digested to `unparsed`. Since unparsed is never
treated as agreement, the orbit reported clean. → lenient extraction for comparison only (§1.3).

### 4.2 The wrong Firefox profile — the cause of every "expired session"
`profiles.ini` holds two profiles: `[Profile1]` marked with the legacy `Default=1`, and
`[InstallXXXX]` whose `Default=<path>` is what modern Firefox actually launches. Preferring
`Default=1` picks a **stale, empty** profile that launches fine and is simply signed out — so the
symptom is not an error but a signed-out page, which reads as "the session expired" and sends
diagnosis in entirely the wrong direction. *The upstream `workaround3_example.py` has the same
ordering and would pick the same empty profile.*

### 4.3 A verification that always passed
Temporary chat was "verified" via `aria-pressed`, which the app never sets — so the check passed
while the mode was off, and the first two candidates were written to history. Worse, the click used
`execute_script`, which the app's own handlers ignore. → real `.click()`, verified by effect.

### 4.4 Refreshing drops the session
A reload issued before the app settles loses the session **permanently** (`signin=2, temp_chat=0`,
never re-hydrates), while the first load is already authenticated. Waiting for hydration is what
matters; the reload is actively harmful here.

### 4.5 `presence_of_element_located` returns too early
the target model serves a signed-out shell that already contains a usable input box, so the DOM being ready is
not the account being ready. Acting at that moment reads the wrong UI entirely.

---

## 5. Limits on these results

- **One account, one day, one task family.** Not reproducible in the strict sense the rest of this
  framework insists on — a hosted UI cannot offer that, and the provider may change the model
  underneath at any time. Every figure here is evidence about *a target on a date*.
- **Three tasks is a small sample.** The capability figures in particular rest on 36 requests each.
- **The transport is fragile by nature.** Selectors change without notice; this is not an API
  contract and should not be treated as a durable measurement channel.
- **Instability confounds §2's fragility and invariance figures** (§3.2). Reporting them without that
  caveat would be the single most misleading thing this document could do.
- **A larger K is required for a real fragility number.** With 3 distinct answers appearing in 3
  tries, K=3 is barely enough to detect instability and not enough to average it out.

## 6. Reproducing

> **The raw data from the 2026-08-06 run is lost.** The runner and its
> `model_k3.json` output were written to a temporary directory rather than the
> repository, and were deleted when `/tmp` was cleaned. The figures in §2–§3 are all that
> survives of that execution, and **no reader can independently re-check them** — they must be
> taken as a report, not as inspectable evidence. Re-running the command below produces a fresh
> dataset, which will not be identical: the target is non-deterministic (§3.2) and hosted.
>
> This was avoidable, and it is the same defect this document criticises elsewhere: a claim of
> reproducibility that the artefacts did not support. The runner now lives in the repository so
> the claim is true going forward.

```bash
cd generator_trunk/AI_combi_testing_platform
export AI_COMBI_ALLOW_BROWSER=1              # separate opt-in from the API adapter gate

python3 experiments/preflight_browser.py     # ~1 min: checks every known failure mode first
python3 experiments/run_model_k3.py     # 108 requests, ~30 min
```

A 108-request run costs about half an hour, so the preflight is worth the minute: it verifies
profile resolution, session hydration, model pinning, temporary chat and reply extraction —
each of which failed at least once while this was built (§4).

| Artefact | Path |
| --- | --- |
| runner (K=3, 3 tasks) | `experiments/run_model_k3.py` |
| preflight | `experiments/preflight_browser.py` |
| individual diagnostics | `experiments/probes/probe_{profile,target_model,models,temp_chat,session}.py` |
| adapter | `adapters/browser.py` (`BrowserChatAdapter`) |
| output of a run | `experiments/model_k3.json` (override with `AI_COMBI_RUN_OUT`) |

Each probe isolates one failure mode and can be run alone; `probe_profile.py` needs no browser at
all and is the cheapest check that the right Firefox profile is being used (§4.2).

Adapter behaviour: headless Firefox, derived profile carrying session files only (the operator's
real profile is never opened for writing), temporary chat re-engaged per candidate, model pinned
explicitly, and fail-closed on any inability to read a reply — it never fabricates or guesses a
response.
