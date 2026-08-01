# Run report — 15_secondorder_group_rewrite

- spec: `llm_selfposed_bundle_tasks/15_secondorder_group_rewrite/scenario.toml`  sha256 `3c32a2ae96d7325d...`
- category: second-order recombination (FW_Group + FW_ReplaceRE + FW_Separator)  | pattern: group_sep_demo + ZEN canonical FW_Group
- plan: final=8 mode=EXACT run_class=S
- PLAN + GRAPH ONLY: Second-order FW_Group: the planner estimates only the base verb (FW_Subsets=8) and cannot fold in FW_Group's recombination, so it under-counts. A forced full run materialized fw_final=206 in Core (vs estimate 8) and tripped the CRITICAL reader_emitted_eq_expected invariant (expected 8, got 206). Hence PLAN + GRAPH only in the safe path (like the brace, scenario 06); a real second-order run needs explicit handling, not the default invariant chain.
