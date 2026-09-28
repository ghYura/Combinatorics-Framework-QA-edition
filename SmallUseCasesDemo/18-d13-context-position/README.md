<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13e — Context order and noisy judges

[Contract](CONTRACT.md) · [Predictions](architect-derived.json)

An eight-order SCA3 cover misses a third-position defect despite covering every
ordered triple. A separate position control exposes it. Labelled public/secret
tasks also calibrate two noisy judge surrogates against mechanical truth.

Plan EXACT 54 candidates; 20 internal trials each, 1080 trials and 2160 judge
readings. Predicted 49 PASS / 5 DOMAIN_FAIL. Framework repeat=1. The fixed noise
fixture and illustrative intervals make no claim about live models or judges.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d13e_20260928T171251Z` on Framework v6 (no change), no sieve.
- **Counts:** plans EXACT 54 (XLSX = TOML, the AI architect's graph hash); Core 54 = Reader = Executor = results_v2;
  1080 internal trials, 2160 judge readings; Framework repeat 1.
- **Outcomes:** **49 PASS / 5 DOMAIN_FAIL** (verify 35/35 at campaign time, 49,788 record fields). The SCA3
  cover finds 4 last_marker failures and misses third_position; the ABGCDE control catches it.
- **Judges:** all four calibration cells equal the frozen values; late band agree exactly, early band
  disagree on 239 draws with FT = 0 (the declared coupling). Wilson intervals are illustrative only.
- Five replays were byte-identical. No external models, judges or outbound actions.
