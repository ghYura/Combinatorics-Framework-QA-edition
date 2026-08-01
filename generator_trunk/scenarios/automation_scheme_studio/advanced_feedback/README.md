# Advanced recursive feedback architecture suite

This suite searches executable SUT control circuits, not string labels or a
surrogate model. Bundle-generated code forms an immutable recursive topology:

- `sequence(children...)`
- `parallel(children..., reducer=mean|sum|signed)`
- `repeat(body, count, mode=series|parallel)`
- `feedback(body, controller, state boundary, placement)`
- any of those nodes nested inside any other node

The adapter registers the resulting program as a `SearchPlan` feedback cell.
The SUT builder creates the real nodes and connections, the SUT compiler checks
cycles and terminal types, the SUT runtime executes the excitation battery, and
the existing Oracle emits the seven Analyzer objectives.

Scenarios:

- `00_smoke`: 32 bounded candidates proving nested, parallel, and repeated
  feedback circuits compile and execute end to end.
- `01_operator_smoke`: a tiny runtime-cardinality proof that executes
  `FW_Group` and a three-link nested-brace chain through the real Core/Reader (8 non-duplicated generated circuits; 4 Oracle PASS in the checked smoke).
- `10_third_order_brace`: a true three-level nested brace chain. It combines
  all ordered pairs of all 16 SUT stage types, a tail boundary, repeated
  complex-loop branches, return-path subsets, and eight outer policies.
- `20_grouped_repetition`: `FW_Group` combinations-of-combinations feed a
  brace together with `FW_PermutR`; a nested brace adds the outer feedback.

Intermediate brace targets are `FW_Exclude` assembly temporaries, so only the
highest-order result enters the final Cartesian product; the operator smoke pins
this invariant at 8 rather than 512 redundant candidates.

The heavy scenarios have runtime-known cardinality because higher-order result
tables are inputs to later operators. The launcher therefore requires the
Bundle's explicit extreme-run acknowledgment, uses sharded candidates, runs
the parallel Python Executor, and produces a combined exact formal Pareto
report only after both campaigns complete.

Commands:

```bash
python3 run_advanced_campaign.py plan
python3 run_advanced_campaign.py smoke
python3 run_advanced_campaign.py run
```

For `smoke` and `run`, set `BUNDLE_MAIN_DB_PASSWORD` and
`BUNDLE_RESULTS_DB_PASSWORD`. Runtime data defaults to `/tmp/fw_work`;
combined reports are written to `campaign_results/`.
