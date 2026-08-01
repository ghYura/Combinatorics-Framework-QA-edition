# llm_arch_search — combinatorial LLM-Transformer architecture search on the Bundle

*Initial implementation: Claude (Opus 4.8). Independent audit and verification
extensions: Automation (GPT-5), 2026-06-13. The dated results below are a
historical campaign record; its generated report files are not checked into the
current tree. This suite uses the Bundle
(Combinatorics Framework) to **generate** Transformer architecture variants and **test
each comprehensively** — the safe, fail-loud counter-design to the "universal polymorphic
Transformer constructor" reviewed in `…/llm_transformer_testme/`.*

## The idea in one line

The LLM-transformer conversations wanted an engine that combinatorially swaps architectural
components and finds good ones. Both reviewing AIs (Opus, Automation) concluded the missing safe
substrate is a **typed catalog → compatibility compiler → search → evaluator** loop. **The
Bundle already is that loop.** This suite plugs Transformer components into it:

| NAS need | Bundle layer | here |
|---|---|---|
| discrete design space | **mechanics** (verbs) | `FW_Combi(1)` component choices, `FW_Permut` layer order, `FW_Optional` plugins |
| reject invalid compositions | **bonds** (sieve) | `arch_compat`: `n_heads` must divide `d_model` — pruned before build |
| build + measure once | **meaning** (oracle) | `arch_zoo.evaluate` — build + forward + backward + zero-cost proxies |
| select | **Analyzer** | formal Pareto over `params:min, latency_ms:min, proxy_gradnorm:max` |

`arch_zoo.py` is the **typed, fail-loud component catalog** the constructor lacked: it
**raises** on an incompatible genotype (it never auto-projects / auto-synthesises), and
residual-vs-replace is **explicit**, never inferred from tensor shape.

## Components (`arch_zoo.py`)

- **norms** (`replace`): `rmsnorm`, `layernorm`
- **token mixers** (causal, residual): `mhsa` (O(S²)), `swa` (sliding window), `linattn`
  (real causal O(S) feature-map — *no* S×S matrix, unlike the reviewed "falsely quadratic" one)
- **channel mixers** (residual): `swiglu`, `moe` (top-k routing + load-balance aux loss;
  experts are evaluated over a common token matrix so suffix routing cannot perturb prefix GEMM shapes)
- **block**: explicit pre-norm or post-norm residual policy
- **plugins**: weight-tying, extra final norm, wide FFN
- **`build_model(geno)`**: genotype → `TinyLM`, fail-loud validation
- **`evaluate(geno)`**: a structural oracle: shape, finite output/loss, exact causal
  isolation at every prefix boundary, deterministic eval, full gradient accounting, a real
  parameter update, and same-batch objective reduction. Detailed codes: `1` shape, `2`
  non-finite, `3` gradients, `4` causality, `5` determinism, `6` optimizer did not reduce
  the objective, `8` incompatible genotype/config, `9` unexpected crash.
- **Verdict transport**: `FW_VAR` is deliberately binary (`0` pass, `1` domain failure) because
  Bundle positional mode bounds it by the number of combination columns. `FW_CUSTOM_VAR`
  and the emitted `code` preserve the detailed oracle diagnosis.
- **Metrics**: parameters/model bytes, median warmed inference latency, throughput, total audit
  time, before/after loss and improvement, output standard deviation, gradient and nonzero-gradient
  coverage, update norm, causal-check count, determinism, benchmark thread count, and MoE auxiliary
  loss. They are cheap proxies, not trained quality.

## The four specs (each a Bundle spec dir)

| spec | verb(s) | space | what it searches |
|---|---|---|---|
| `arch_grid` | `FW_Combi(1)`⁵ | **48** EXACT | norm × token-mix × channel-mix × pre/post-norm × depth |
| `arch_order` | `FW_Permut` | **6** EXACT (3!) | layer **ordering** of a 3-block hybrid (the T-M-T-M question) |
| `arch_optional` | `FW_Combi(1)` × `FW_Optional`³ | **24** EXACT (3×2³) | base × present/absent plugins |
| `arch_compat` | `FW_Combi(1)`² + **sieve** | 9 → **8** | d_model × n_heads, pruning indivisible heads |

## Run it

```bash
cd .../generator_trunk
: "${BUNDLE_MAIN_DB_PASSWORD:?inject the main DB password for --full}"
: "${BUNDLE_RESULTS_DB_PASSWORD:?inject the results DB password for --full}"

# Local checks + plans, no DB; writes verification_plan_report.json:
python3 llm_arch_search/run_suite.py

# Checks + plans + all PostgreSQL chains + no-sieve defense case;
# writes verification_report.json and removes its temporary DBs:
python3 llm_arch_search/run_suite.py --full --workers 4

# Retain temporary DBs only when they are needed for manual inspection:
python3 llm_arch_search/run_suite.py --full --keep-dbs
```

The runner rejects unsafe prefixes and pre-existing database collisions, honors custom ports and
scratch roots, writes partial evidence on failure, checks the exact no-sieve code-8 row, and fails if
counts, outcomes, Analyzer input counts, or provenance disagree. Full runs remove only databases they
proved absent before the run; `--keep-dbs` opts out. The specs import the local `arch_zoo` path, so they
support `trusted-local` execution only. Secure/container execution requires vendoring `arch_zoo` into
each generated candidate or packaging it as a mounted dependency.

## Historical verification record (2026-06-13)

On the recorded FX-8320 / torch 2.12.0+cpu / trusted-local campaign, all four
specs ran green through the full chain (Generator → Core → [sieve] → Reader →
Executor → formal Analyzer), and candidate counts reconciled at every stage:

| spec | generated | Executor | Pareto front |
|---|---|---|---|
| `arch_grid` | `fw_final=48` → 48 candidates | **48 PASS / 0 fail** | 10 non-dominated |
| `arch_order` | `fw_final=6` (3!) | **6 PASS / 0 fail** | 2 |
| `arch_optional` | `fw_final=3` × optional → 24 | **24 PASS / 0 fail** | 4 |
| `arch_compat` | `fw_final=9` → **sieve removes 1** → 8 | **8 PASS / 0 fail** | 6 |

The required defense run omits the sieve and produces **8 PASS + 1 DOMAIN_FAIL**. The invalid
`(d_model=64, n_heads=6)` candidate emits detailed code `8`; there are no broken, timeout, or
infrastructure outcomes. With the sieve enabled, that row is removed before model construction.
The 2026-06-13 audit also verified a custom scratch root, exact defense evidence, compact reports,
and cleanup of all five test database names on both PostgreSQL clusters.

Those raw run directories and `verification_{plan_,}report.json` outputs are
absent from this checkout. Run `run_suite.py` again and retain its generated
reports and run artifacts before making a current verification claim.

## Honest limitations (what this is and isn't)

1. **The oracle is a zero-cost proxy, not trained quality.** `proxy_gradnorm`, parameters, and
   latency are cheap signals. Swap in a
   real proxy (SynFlow/NASWOT) or a few-step train as the oracle when hardware allows.
2. **This suite is single-pass.** `run_suite.py` enumerates → prunes →
   evaluates → selects once. The wider Bundle now has seed-bias and journaled
   iteration modes, but this suite does not wire its Analyzer results back into
   those controls. Large `nᵏ` spaces still need an explicitly configured outer
   search policy.
3. **This suite authors only one binary compatibility rule.** The current sieve
   is not binary-only: it evaluates n-ary `pairs`/`sets`/`when` rules,
   contextual `condition`, dependent `mapping`, and unary/n-ary `assert`
   relations. No n-ary architecture rule is exercised here, so add and test one
   before claiming that coverage. Rules touching `FW_Optional` are deferred to
   Reader assembly; unsupported contextual/absence-sensitive forms fail closed
   instead of being silently weakened.
4. **Trusted-local dependency:** candidate source imports `arch_zoo` from this checkout. Vendor
   it before treating generated candidates as portable or untrusted inputs.
5. **Dense MoE evaluation:** routing is top-k semantically, but this tiny reference evaluates every
   expert over a common token matrix to guarantee bit-exact causal auditing. A production sparse MoE
   needs a routing kernel whose prefix arithmetic is independent of suffix assignments.
6. **Counts:** first-order verbs are EXACT (plannable/budgetable — an edge over blind NAS);
   the sieve makes `arch_compat` BOUNDED until it runs. Pareto-front size can vary between runs because
   latency is a measured objective; candidate and verdict counts are the invariant checks.

## Files

```
llm_arch_search/
  arch_zoo.py            # typed, fail-loud component catalog + build_model + evaluate (oracle)
  _selfcheck.py          # standalone structural audit of all 48 grid variants
  test_arch_search.py    # semantic, factory, oracle, cardinality, transport regressions
  run_suite.py           # checks, plans, full chains, strict assertions, JSON report
  verification_plan_report.json # generated by run_suite.py; absent before a run
  verification_report.json      # generated by run_suite.py --full
  arch_grid/arch_grid.toml
  arch_order/arch_order.toml
  arch_optional/arch_optional.toml
  arch_compat/arch_compat.toml
  README.md
```
