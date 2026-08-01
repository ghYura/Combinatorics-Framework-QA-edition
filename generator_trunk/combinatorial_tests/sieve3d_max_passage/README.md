# sieve3d maximum-passage use cases

The proof-bearing use case is
`equivalence_size_first/staged_passage_search.py`; despite the historical
directory name, it now performs a fixed-pair, all-body/all-hole neutral-first
search with persistent minimality/exhaustion certificates.  See
`equivalence_size_first/README.md` for construction, Bundle/Analyzer commands,
evidence layout, exact cost semantics, and GUI replay.

`api_planner_feedback/` remains a small compatibility probe for the SUT's
planner/features routes and rich motion-frame recording.  Its outcomes are not
used to override a cheaper exact static solution in the staged proof.
