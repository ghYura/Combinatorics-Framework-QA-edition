# GUI constraints e2e fixture

This fixture is intentionally small but end-to-end. It models a checkout risk
engine with five independent variation sheets. The TOML spec starts without
constraints; tests simulate a GUI save by feeding Bundle the same sidecar shape
that the constraints editor writes. Python snippets intentionally do not carry
per-value trailing newlines; Bundle asks Reader to insert `reader.core.concatenator=\n`.

The downstream Python object is `CheckoutRiskEngine`, embedded in the HEAD slot
so generated candidates are self-contained. The TAIL slot emits K=V metrics and
sets `FW_VAR=2` if any structurally invalid combination reaches runtime. A
passing e2e run therefore proves both that the sieve removed invalid GUI-authored
combinations and that the surviving candidates remain executable by the normal
Bundle workflow.

The GUI-authored rules cover:

- singleton pair forbid: `partner` channel cannot use `invoice`;
- multi-value/n-ary set forbid: `invoice` or `wire` cannot be `eu` + `express`;
- formula/when forbid over GUI params: high payment/review risk is rejected;
- singleton n-ary forbid: `ivr` + `wire` + `auto` is rejected.
