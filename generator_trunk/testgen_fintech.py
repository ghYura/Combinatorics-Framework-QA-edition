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

r"""Finance-stack client-server combinatorial test design.

Decomposes the finance stack (client→server1→server2) into logical pieces and
distributes each piece to the combination rule that semantically breeds new tests:

  • orthogonal request dims  → CARTESIAN  (FW_Combi(1))  — protocol/auth/currency/amount
  • ORDER-sensitive op seqs  → PERMUTATIONS (FW_Permut)  — state-ordering bugs
  • optional request fields  → SUBSETS    (FW_Subsets)   — validation-gap bugs
  • compound fault injection → COMBI C(n,2) (FW_Combi(2))— compound-error edge cases

Total space:  5×2×4×5×5  ×  4!  ×  2^4  ×  C(6,2)  =  5 760 000  runnable tests

Emits:
  generated_tests_fintech/  — real runnable Python test scripts (curated + random)
  scenarios/fintech_client_server/fintech_materialized.xlsx
  scenarios/fintech_client_server/fintech_native_fwseq.xlsx

Run:
  python3 testgen_fintech.py
  python3 generated_tests_fintech/00_baseline_happy_path.py
"""
from __future__ import annotations

import itertools
import random
import re
import subprocess
import sys
from pathlib import Path

import fwgen as fg
from openpyxl import Workbook

from sut_paths import project_path

HERE         = Path(__file__).resolve().parent
HARNESS      = (HERE / "scenarios" / "fintech_client_server" / "harness.py").read_text(encoding="utf-8")
OUT_TESTS    = HERE / "generated_tests_fintech"
OUT_XLSX     = HERE / "scenarios" / "fintech_client_server"
FINTECH_SRC  = str(project_path("fintech"))

# ---------------------------------------------------------------------------
# 1. Decomposition — each logical piece + the combination rule that fits it
# ---------------------------------------------------------------------------
CARTESIAN = [   # orthogonal request/protocol/auth/money dimensions → FW_Combi(1)
    ("OPERATION", "op",       ["create_account", "credit", "debit", "transfer", "balance_inquiry"]),
    ("PROTOCOL",  "protocol", ["json", "soap"]),
    ("AUTH",      "auth",     ["valid_hmac", "missing_headers", "bad_signature", "expired_timestamp"]),
    ("CURRENCY",  "currency", ["USD", "EUR", "usd", "XX", ""]),
    ("AMOUNT",    "amount",   ["100.00", "0.00", "-1.00", "0.001", "9999999999.99"]),
]

PERMUT_OPS     = ["create_account", "credit", "debit", "balance_inquiry"]   # FW_Permut → 4! = 24
SUBSET_FIELDS  = ["owner_name_explicit", "initial_balance",                  # FW_Subsets → 2^4 = 16
                  "source_acc_explicit",  "note"]
COMBI_FAULTS   = ["currency_mismatch", "account_frozen",                     # FW_Combi(2) → C(6,2)=15
                  "insufficient_funds",  "bad_idempotency_key",
                  "missing_required_field", "wrong_amount_format"]
SUDDEN_VALUES  = ["freeze_mid_debit", "replay_attack",                       # FW_Optional → present|absent
                  "concurrent_credit", "noop"]

VERDICTS = [
    (2, "unexpected crash / unhandled exception in service or security layer"),
    (3, "domain invariant violated (wrong error, missing error, wrong status)"),
    (4, "HMAC security bypass (bad auth accepted by verify_request)"),
    (5, "currency normalisation failure (usd vs USD divergence)"),
    (6, "wrong final transaction status (not SETTLED/REJECTED as expected)"),
]

# ---------------------------------------------------------------------------
# 2. Rule expansions  (mirror what the Core verbs produce)
# ---------------------------------------------------------------------------
def permutations_of(xs):       return list(itertools.permutations(xs))
def subsets_of(xs):            return [list(c) for r in range(len(xs) + 1)
                                        for c in itertools.combinations(xs, r)]
def kcombos_of(xs, k):         return [list(c) for c in itertools.combinations(xs, k)]

OP_VALUES     = permutations_of(PERMUT_OPS)     # 24
FIELD_VALUES  = subsets_of(SUBSET_FIELDS)       # 16
FAULT_VALUES  = kcombos_of(COMBI_FAULTS, 2)     # 15

def space_size():
    n = 1
    for _, _, vals in CARTESIAN:
        n *= len(vals)
    # SUDDEN is FW_Optional: Core generates 2 variants per combination (with / without sudden)
    return n * len(OP_VALUES) * len(FIELD_VALUES) * len(FAULT_VALUES) * 2

# ---------------------------------------------------------------------------
# 3. Assemble a real Python test from one combination
# ---------------------------------------------------------------------------
def _pyrepr(v):
    if isinstance(v, list):
        return repr(v)
    return repr(str(v))

SLOTS_RE = re.compile(r"(?ms)^# SLOTS-BEGIN\n.*?^# SLOTS-END\n?")


def _split_harness() -> tuple[str, str]:
    head, rest = HARNESS.split("# SLOTS-BEGIN", 1)
    _slots, tail = rest.split("# SLOTS-END", 1)
    return head.rstrip() + "\n", tail.lstrip("\n")


def assemble(op, protocol, auth, currency, amount, ops, fields, faults,
             sudden="") -> str:
    slot_lines = [
        f"OPERATION   = {_pyrepr(op)}",
        f"PROTOCOL    = {_pyrepr(protocol)}",
        f"AUTH        = {_pyrepr(auth)}",
        f"CURRENCY    = {_pyrepr(currency)}",
        f"AMOUNT      = {_pyrepr(amount)}",
        f"OP_SEQUENCE = {_pyrepr(list(ops))}",
        f"OPT_FIELDS  = {_pyrepr(list(fields))}",
        f"FAULTS      = {_pyrepr(list(faults))}",
        f"SUDDEN      = {_pyrepr(sudden)}",
    ]
    block = "\n".join(slot_lines)
    return SLOTS_RE.sub(block + "\n", HARNESS)

# ---------------------------------------------------------------------------
# 4. Curated "unexpected" combinations + baseline + random sample
#    combo = (op, protocol, auth, currency, amount, ops, fields, faults)
# ---------------------------------------------------------------------------
def combo(op="create_account", protocol="json", auth="valid_hmac",
          currency="USD", amount="100.00",
          ops=("create_account", "credit", "balance_inquiry", "debit"),
          fields=(), faults=(), sudden=""):
    return (op, protocol, auth, currency, amount,
            list(ops), list(fields), list(faults), sudden)

CURATED = [
    ("baseline_happy_path",
     combo(),
     "Happy path: create → credit → balance_inquiry → debit, valid HMAC, USD 100, no sudden."),

    ("debit_before_create",
     combo(op="debit", ops=("debit", "create_account", "credit"), amount="50.00"),
     "PERMUT bug-hunt: debit before account exists → Skipped/NotFoundError, not crash."),

    ("credit_then_transfer_no_target",
     combo(op="transfer", ops=("create_account", "credit", "transfer"), amount="50.00"),
     "PERMUT: transfer with only 1 account → Skipped (not crash), no 500."),

    ("hmac_missing_headers",
     combo(auth="missing_headers"),
     "AUTH: missing HMAC headers → verify_request must return (False, missing_auth_headers)."),

    ("hmac_bad_signature",
     combo(auth="bad_signature"),
     "AUTH: corrupted signature → verify_request must return (False, bad_signature)."),

    ("hmac_expired_timestamp",
     combo(auth="expired_timestamp"),
     "AUTH: timestamp outside replay window → (False, timestamp_out_of_window)."),

    ("sudden_freeze_mid_debit",
     combo(ops=("create_account", "credit", "debit"), sudden="freeze_mid_debit"),
     "FW_Optional SUDDEN: account frozen mid-flight before debit → ValidationError (not crash)."),

    ("sudden_replay_attack",
     combo(ops=("create_account",), sudden="replay_attack"),
     "FW_Optional SUDDEN: replay-attack with expired timestamp → timestamp_out_of_window."),

    ("sudden_concurrent_credit",
     combo(ops=("create_account", "debit"), amount="50.00", sudden="concurrent_credit"),
     "FW_Optional SUDDEN: concurrent credit fires mid-sequence — balance must stay non-negative."),

    ("currency_lowercase_normalisation",
     combo(currency="usd", ops=("create_account", "balance_inquiry")),
     "CARTESIAN: 'usd' → Money.normalized() must uppercase to 'USD'; balance_inquiry succeeds."),

    ("invalid_currency_XX",
     combo(currency="XX", ops=("create_account", "credit", "debit"), amount="10.00"),
     "CARTESIAN: non-ISO currency 'XX' — service stores it; no crash expected."),

    ("amount_zero_credit",
     combo(op="credit", amount="0.00", ops=("create_account", "credit")),
     "CARTESIAN: amount=0.00 → ValidationError('amount must be positive') on credit."),

    ("amount_negative_debit",
     combo(op="debit", amount="-1.00", ops=("create_account", "debit")),
     "CARTESIAN: amount=-1.00 → ValidationError on debit (not crash)."),

    ("amount_fractional_excess",
     combo(amount="0.001", ops=("create_account", "credit"), op="credit"),
     "CARTESIAN: 0.001 rounds to 0.00 → ValidationError 'amount must be positive' on credit."),

    ("frozen_account_debit",
     combo(faults=("account_frozen",), ops=("create_account", "debit")),
     "FAULT: account_frozen set before debit → ValidationError 'account is not active'."),

    ("insufficient_funds_debit",
     combo(faults=("insufficient_funds",),
           ops=("create_account", "debit"), amount="9999999999.99"),
     "FAULT: debit amount > balance → InsufficientFundsError must be raised."),

    ("compound_frozen_and_mismatch",
     combo(faults=("account_frozen", "currency_mismatch"),
           ops=("create_account", "debit")),
     "COMBI(2): frozen account + currency mismatch simultaneously — which error fires first?"),

    ("compound_wrong_format_and_mismatch",
     combo(faults=("wrong_amount_format", "currency_mismatch"),
           ops=("create_account", "credit")),
     "COMBI(2): NaN amount + wrong currency — service must raise, not crash with exit(2)."),

    ("workflow_reserve_violation",
     combo(op="transfer", auth="valid_hmac", currency="USD", amount="480.00",
           ops=("create_account",)),
     "WORKFLOW: transfer_amount=480 > available_balance(500×0.9=450) → WorkflowInputError."),

    ("soap_protocol_happy_path",
     combo(protocol="soap"),
     "CARTESIAN: protocol=soap — auth + service layer tested; SOAP transport flag recorded."),

    ("full_crud_permut_reverse",
     combo(ops=("debit", "balance_inquiry", "credit", "create_account")),
     "PERMUT: reverse order — debit/balance before create → Skipped not crash; create at end."),

    ("sudden_noop_baseline",
     combo(sudden="noop"),
     "FW_Optional SUDDEN=noop: explicit no-op variant — baseline for sudden/no-sudden comparison."),
]

def random_sample(n=4, seed=20260601):
    rnd = random.Random(seed)
    cart_vals = [v for _, _, v in CARTESIAN]
    # SUDDEN is FW_Optional: randomly absent (empty string) or present (a value)
    sudden_choices = [""] + SUDDEN_VALUES   # "" = Core excluded slot
    out = []
    for i in range(n):
        c = combo(
            op       = rnd.choice(cart_vals[0]),
            protocol = rnd.choice(cart_vals[1]),
            auth     = rnd.choice(cart_vals[2]),
            currency = rnd.choice(cart_vals[3]),
            amount   = rnd.choice(cart_vals[4]),
            ops      = list(rnd.choice(OP_VALUES)),
            fields   = list(rnd.choice(FIELD_VALUES)),
            faults   = list(rnd.choice(FAULT_VALUES)),
            sudden   = rnd.choice(sudden_choices),
        )
        out.append((f"random_{i+1}", c,
                    "Random draw from full space (seeded) — unexpected test."))
    return out

# ---------------------------------------------------------------------------
# 5. Emit Python test files + manifest
# ---------------------------------------------------------------------------
def emit_tests():
    OUT_TESTS.mkdir(parents=True, exist_ok=True)
    for f in OUT_TESTS.glob("*.py"):
        f.unlink()
    cases   = CURATED + random_sample()
    manifest = ["# Generated Finance-Stack tests — combination → what it probes\n"]
    programs = []
    for i, (name, c, why) in enumerate(cases):
        prog = assemble(*c)
        (OUT_TESTS / f"{i:02d}_{name}.py").write_text(prog, encoding="utf-8")
        programs.append((f"{i:02d}_{name}", prog, c))
        sudden_str = f"  sudden={c[8]!r}" if len(c) > 8 and c[8] else ""
        manifest.append(
            f"- **{i:02d}_{name}** — op={c[0]!r} proto={c[1]!r} auth={c[2]!r} "
            f"cur={c[3]!r} amt={c[4]!r}\n"
            f"  seq={c[5]}  opt={c[6]}  faults={c[7]}{sudden_str}\n"
            f"    ↳ {why}"
        )
    (OUT_TESTS / "MANIFEST.md").write_text("\n".join(manifest), encoding="utf-8")
    return programs

# ---------------------------------------------------------------------------
# 6. Syntax-check generated tests with py_compile
# ---------------------------------------------------------------------------
def syntax_check(programs):
    import py_compile
    ok = 0
    for name, prog, _ in programs:
        src = OUT_TESTS / f"{name}.py"
        try:
            py_compile.compile(str(src), doraise=True)
            ok += 1
        except py_compile.PyCompileError as e:
            print(f"  SYNTAX FAIL {name}: {e}")
    return ok, len(programs)

# ---------------------------------------------------------------------------
# 7. Run the baseline test to verify the harness is correct
# ---------------------------------------------------------------------------
def smoke_run():
    baseline = OUT_TESTS / "00_baseline_happy_path.py"
    result   = subprocess.run(
        [sys.executable, str(baseline)],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()

# ---------------------------------------------------------------------------
# 8. Build materialized XLSX workbook (one row per generated test)
# ---------------------------------------------------------------------------
def build_materialized_workbook(programs):
    spec = fg.parse_spec(fg.build_spec_dict(
        "fintech_client_server_sample",
        [(s, k, v) for (s, k, v) in CARTESIAN],
        title="Finance Stack — materialized combinatorial test sample",
        goals=["bugs_found", "coverage"],
        custom_vars=VERDICTS,
    ), "fintech_client_server_sample")
    # Each generated test → one CANDIDATE row (its slot header comment)
    rows = []
    for name, prog, c in programs:
        sudden_part = f" sudden={c[8]}" if len(c) > 8 and c[8] else ""
        row_label = (
            f" op={c[0]} protocol={c[1]} auth={c[2]} currency={c[3]} amount={c[4]}"
            f" seq={c[5]} opt={c[6]} faults={c[7]}{sudden_part}"
        )
        rows.append(row_label)
    path  = OUT_XLSX / "fintech_materialized.xlsx"
    fg.build_materialized(spec, rows, data_sheet="CANDIDATE").save(path)
    return path, fg.validate_workbook(path)

# ---------------------------------------------------------------------------
# 9. Build native FW_Seq XLSX (Core expands — elegant rule-distribution form)
# ---------------------------------------------------------------------------
def build_native_fwseq_workbook():
    """The elegant native representation: each logical piece is a separate data
    sheet driven by the rule that semantically fits it.  The Core applies all
    rules and concatenates to produce runnable candidates.

    Rule distribution:
      CARTESIAN slots → FW_Combi(1)  (independent dims, cartesian product)
      OP_SEQUENCE     → FW_Permut    (order-sensitive — catches state bugs)
      OPT_FIELDS      → FW_Subsets   (optional fields present/absent)
      FAULTS          → FW_Combi(2)  (compound fault pairs)
    """
    wb = Workbook()
    seq = wb.active
    seq.title = "FW_Seq"

    # (sheet, flags, verb)  — SUDDEN gets FW_Reuse + FW_Optional (two flags)
    seq_rows = [
        ("HEAD",          ("FW_Reuse",),                        "FW_Combi(1)"),
        ("OPERATION",     ("FW_Reuse",),                        "FW_Combi(1)"),
        ("PROTOCOL",      ("FW_Reuse",),                        "FW_Combi(1)"),
        ("AUTH",          ("FW_Reuse",),                        "FW_Combi(1)"),
        ("CURRENCY",      ("FW_Reuse",),                        "FW_Combi(1)"),
        ("AMOUNT",        ("FW_Reuse",),                        "FW_Combi(1)"),
        ("OP_SEQUENCE",   ("FW_Reuse",),                        "FW_Permut"),
        ("OPT_FIELDS",    ("FW_Reuse",),                        "FW_Subsets"),
        ("FAULTS",        ("FW_Reuse",),                        "FW_Combi(2)"),
        # FW_Optional: Core includes this slot in SOME combos, excludes in others.
        # Models "sudden actions" — mid-flight surprises that may or may not fire.
        ("SUDDEN",        ("FW_Reuse", "FW_Optional"),          "FW_Combi(1)"),
        ("TAIL",          ("FW_Reuse",),                        "FW_Combi(1)"),
    ]
    for i, (sh, flags, verb) in enumerate(seq_rows, 1):
        seq.cell(i, 1, sh)
        col = 2
        for f in flags:
            seq.cell(i, col, f)
            col += 1
        seq.cell(i, max(col, 4), verb)

    # FW_SheetNames: prefix/ending wrap each value into a Python assignment statement
    nm = wb.create_sheet("FW_SheetNames")
    NL = "\n"
    names = {
        "HEAD":        ("FW_EMPTY_STRING", "FW_EMPTY_STRING"),
        "OPERATION":   ('OPERATION   = "',  '"' + NL),
        "PROTOCOL":    ('PROTOCOL    = "',  '"' + NL),
        "AUTH":        ('AUTH        = "',  '"' + NL),
        "CURRENCY":    ('CURRENCY    = "',  '"' + NL),
        "AMOUNT":      ('AMOUNT      = "',  '"' + NL),
        "OP_SEQUENCE": ('OP_SEQUENCE = [',  ']' + NL),
        "OPT_FIELDS":  ('OPT_FIELDS  = [',  ']' + NL),
        "FAULTS":      ('FAULTS      = [',  ']' + NL),
        "SUDDEN":      ('SUDDEN      = "',  '"' + NL),
        "TAIL":        ("FW_EMPTY_STRING", "FW_EMPTY_STRING"),
    }
    for i, (sh, _, _) in enumerate(seq_rows, 1):
        pre, end = names[sh]
        nm.cell(i, 1, sh)
        nm.cell(i, 2, pre)
        nm.cell(i, 3, end)

    wb.create_sheet("FW_RunMeFirstOnce").cell(1, 1, "FW_EMPTY_STRING")
    aw = wb.create_sheet("FW_Arguments")
    aw.cell(1, 1, f"target={FINTECH_SRC}")
    aw.cell(2, 1, "stack=python_inmemory")

    cv = wb.create_sheet("FW_CUSTOM_VAR")
    for i, (code, msg) in enumerate(VERDICTS, 1):
        cv.cell(i, 1, int(code))
        cv.cell(i, 2, f"FWCUSTOMVAR={code} {msg}")

    info = wb.create_sheet("FW_Info")
    for row in seq.iter_rows(values_only=True):
        info.append(row)

    # Data sheets
    head_src, tail_src = _split_harness()

    data: dict[str, list[str]] = {
        "HEAD":        [head_src],
        "TAIL":        [tail_src],
        "OPERATION":   CARTESIAN[0][2],
        "PROTOCOL":    CARTESIAN[1][2],
        "AUTH":        CARTESIAN[2][2],
        "CURRENCY":    CARTESIAN[3][2],
        "AMOUNT":      CARTESIAN[4][2],
        "OP_SEQUENCE": PERMUT_OPS,        # permuted by Core (FW_Permut)
        "OPT_FIELDS":  SUBSET_FIELDS,     # subsetted by Core (FW_Subsets)
        "FAULTS":      COMBI_FAULTS,      # C(6,2) pairs by Core (FW_Combi(2))
        "SUDDEN":      SUDDEN_VALUES,     # optional by Core (FW_Optional) — fires or not
    }
    for sh, _, _ in seq_rows:
        ws = wb.create_sheet(sh)
        for r, v in enumerate(data[sh], 1):
            ws.cell(r, 1, str(v))

    path = OUT_XLSX / "fintech_native_fwseq.xlsx"
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 72)
    print("Finance Stack — client-server combinatorial test design")
    print("=" * 72)

    print("\nRule distribution & space:")
    cart = 1
    for sh, _, vals in CARTESIAN:
        print(f"  {sh:<12} {len(vals):>3}  → FW_Combi(1)  [cartesian dim]")
        cart *= len(vals)
    print(f"  {'OP_SEQUENCE':<12} {len(OP_VALUES):>3}  → FW_Permut    "
          f"[order-sensitive: {PERMUT_OPS}]")
    print(f"  {'OPT_FIELDS':<12} {len(FIELD_VALUES):>3}  → FW_Subsets   "
          f"[2^{len(SUBSET_FIELDS)} optional-field combos]")
    print(f"  {'FAULTS':<12} {len(FAULT_VALUES):>3}  → FW_Combi(2)  "
          f"[C({len(COMBI_FAULTS)},2) compound-fault pairs]")
    print(f"  {'SUDDEN':<12} {'×2':>3}  → FW_Optional  "
          f"[present|absent — {len(SUDDEN_VALUES)} sudden-action variants]")
    print(f"\n  cartesian block = {cart}   →  TOTAL SPACE = {space_size():,} runnable tests")

    progs = emit_tests()
    print(f"\nEmitted {len(progs)} Python tests → {OUT_TESTS.relative_to(HERE)}/  (+ MANIFEST.md)")

    ok, tot = syntax_check(progs)
    print(f"py_compile syntax-check: {ok}/{tot} valid")

    print("\nSmoke-running baseline test …")
    rc, stdout, stderr = smoke_run()
    status = "PASS" if rc == 0 else f"FAIL(exit={rc})"
    print(f"  {status}")
    if stdout:
        print(f"  stdout: {stdout}")
    if stderr:
        print(f"  stderr: {stderr}")

    mpath, merrs = build_materialized_workbook(progs)
    print(f"\nmaterialized workbook → {mpath.name}  "
          f"[{'VALID' if not merrs else '; '.join(merrs)}]")

    npath = build_native_fwseq_workbook()
    print(f"native FW_Seq workbook → {npath.name}  "
          f"(rule distribution: Combi(1)×5 + Permut + Subsets + Combi(2) + FW_SheetNames)")

    print("\n----- example UNEXPECTED test (frozen_account_debit) -----")
    eg_name, eg_combo, eg_why = CURATED[13]   # frozen_account_debit
    eg_prog = assemble(*eg_combo)
    for line in eg_prog.splitlines():
        if any(kw in line for kw in ("OPERATION", "AUTH", "CURRENCY", "AMOUNT",
                                      "OP_SEQUENCE", "FAULTS")):
            print(f"  {line.strip()}")
    print(f"  # {eg_why}")
