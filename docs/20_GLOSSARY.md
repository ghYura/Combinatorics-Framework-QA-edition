# 20 — Glossary

## Bundle-specific terms

- **Bundle / Combinatorics Framework** — the five-component chain
  `generator_trunk → Core_trunk → Reader_trunk → Executor_trunk → Analyzer_trunk` plus the
  control-plane `bundle` package.
- **Control plane / data plane** — the orchestration package vs the five worker components.
- **Mechanics / bonds / meaning** — the three layers: verbs build the space; the sieve forbids
  combinations; the verdict judges each candidate.
- **`FW_Seq`** — the ordered sequence of operations (one row per sheet) the Core evaluates; a
  dataflow of result tables.
- **Verb** — a combinatorial operator (`FW_Combi`, `FW_Permut`, `FW_Subsets`, `FW_CombiR`,
  `FW_PermutR`, `FW_Cartes`, `FW_Separator`, `FW_Optional`, brace, `FW_Group`).
- **Sheet** — a named input axis (a slot's values).
- **`FW_Optional` (sudden action)** — a may-or-may-not-fire action placed before the probe;
  multiplies the space by `×(n+1)` per slot, not the mandatory product.
- **Brace `FW_(…)`** — a second-order **join** of two prior result tables (9 fields:
  `start,_,E1,rel,E2,_,end,sep,mult`); operands carry `FW_Exclude`.
- **`FW_Group` + `FW_ReplaceRE`** — second-order **re-combination + rewrite** of one prior result's
  rows; concatenates by index order (most order-sensitive verb).
- **`fw_final`** — the materialized mandatory result table in the main DB. **`fw_opt<i>`** — optional
  combination tables (size-i co-firing sudden actions). **`fw2_<k>`** — a sheet's dual/sub-combo
  output that braces/`FW_Group` consume.
- **Sieve** — the constraint pass that deletes invalid `fw_final` rows between Core and Reader.
- **Candidate** — one reconstructed, executable artifact (`<final>_<opt>_<j>`, e.g. `25_1_2`).
- **`RunMeFirstOnce`** — the programmable run-scoped prologue that establishes shared setup,
  observes runtime context, may preprocess the corpus, and can produce `FW_ARGS` before a Java
  Executor handoff's candidate family is evaluated. It is not a combinatorial axis, HEAD/TAIL, or a
  per-candidate oracle. Python's trusted-local per-candidate preprocessor is a compatibility path
  with different timing semantics.
- **Sink / candidate transport** — the Reader's output: **loose-files** (one file each), **sharded**
  (`*.fwshard`), or live **gRPC**. Current gRPC is Java/verdict/v2/trusted-local only, plaintext,
  and unauthenticated.
- **Handoff v2** — the versioned Reader→Executor manifest (`bundle.handoff/v2`).
- **Oracle / verdict** — the spec's `FW_VAR` / `FW_CUSTOM_VAR` that judges a candidate.
- **Outcome** — canonical class: PASS, DOMAIN_FAIL, BROKEN, TIMEOUT, INFRA_FAIL, SKIPPED, CANCELLED.
- **Execution policy / profile** — the sandbox/resource/network rules a candidate runs under
  (`generated-default`, `networked-api-probe`, `trusted-local`). There is no default profile: a run
  refuses until one is chosen. `trusted-local` is unsandboxed and additionally requires an origin
  classification and a recorded reason.
- **Candidate origin** — the operator's declaration of where candidate source came from
  (`reviewed-checked-in`, `locally-authored`, `generated`, `imported-untrusted`, `network-facing`).
  Never read from the specification; only the first two may use `trusted-local`.
- **Optional-table contract** — the single record of which `fw_opt<size>` tables Core produces (P)
  and the Reader consumes (R), with `R ⊆ P` enforced at plan time and materialization verified
  after Core.
- **Sandbox backend** — Bubblewrap or Container (rootless Docker) isolation; a non-trusted custom
  local backend offers resource controls only, while trusted-local bypasses SandboxBackend entirely.
- **Run directory / `run_id`** — the per-run identity and atomically-maintained artifact tree.
- **Invariant** — a machine-enforced cross-stage count check (CRITICAL fails the run).
- **Run class** — S (smoke) / B (bounded) / L (large) / X (extreme), by final candidate count.
- **Provenance** — the link from a selected (Pareto) candidate back to its source row/verdict.
- **Formal vs exploratory (Analyzer)** — declared-goals-only with corpus check vs auto-discovery.
- **Repeat / `repeat_idx`** — an intentional sample of the same candidate, numbered 0..K−1; it is
  not a retry.
- **`env_id`** — the execution environment assigned to a repeat sample; K=1 compatibility rows use
  the empty string.
- **`attempt`** — an infrastructure retry nested inside one candidate/repeat/environment sample;
  the highest attempt is selected at read time.
- **Executor pool** — launcher-managed N-way Java MainWatch concurrency over Reader round-robin
  loose-file directories. It is different from stress workers and currently requires K=1.
- **Precompiled-container dispatch** — Java Executor path that compiles a candidate container once
  and dispatches invocations without recompiling each row.
- **`BundleControlPlane`** — Java repeat assignment/dispatch/cancellation/backpressure seam for
  local, disperse, and nested policies; broader than the Bundle launcher's current local-only K>1
  runtime.
- **BundleSeed / `iterate`** — Analyzer winner artifact and the bounded feedback loop that biases a
  later run while retaining an exploration floor and support threshold.

## Count vocabulary

- **raw values** — declared values per slot.
- **per-slot Core rows** — `verb_cardinality(slot)`.
- **mandatory Core product** — Π over mandatory (non-Exclude/Heading/Optional) slots.
- **post-sieve** — mandatory minus pruned rows.
- **optional multiplier** — `Π(nᵢ + 1)` over `FW_Optional` slots.
- **final candidates** — post-sieve × optional multiplier (emitted artifacts).
- **C** — distinct final candidates.
- **A (assignment units)** — repeat-policy dispatch units.
- **V (full verdict invocations)** — canonical outcome rows; equals C only for K=1 or
  measurement-only local/disperse repeats.
- **I (measurement opportunities)** — full-verdict plus metric-only invocations.
- **processed** — full verdict invocations (= sum of the seven outcomes).
- **persisted sample** — immutable results row keyed by
  `(run_id,candidate_id,attempt,repeat_idx,env_id)`.
- **ingested** — observed raw Analyzer metric lines; repeat-aware analysis aggregates these to C
  candidate objective vectors and reports missing samples.
- **Exactness:** **EXACT** (closed form), **BOUNDED** `[lo,hi]` (provable range, e.g. post-sieve),
  **ESTIMATED** (with assumptions, e.g. bytes), **UNKNOWN** (brace/`FW_Group` until Core runs).

## Other

- **SUT** — system under test (here, the example FastAPI app the candidates probe).
- **Legacy handshake** — the pre-v2 filesystem protocol (`resultsDbURL`/`insert.sql`/`arguments`/
  `fwVar.shift`/`runmefirstonce.first`), retained as fallback.
- **Canonical truth fixture** — the Core's deterministic multi-million-row invariants
  (`fw_final=4,644,864`, `fw_opt4=33,674,483`).
