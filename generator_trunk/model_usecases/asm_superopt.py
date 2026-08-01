#!/usr/bin/env python3
r"""asm_superopt — hardware-targeted assembly SUPEROPTIMIZATION via combinatorial program building.

A distinct Bundle capability: decompose a hot routine into interchangeable ASSEMBLY pieces, breed
every combination into a real machine-code routine, ASSEMBLE + RUN + TIME each on THIS exact CPU, and
let the verdict pick the fastest CORRECT variant — the optimum *for this hardware*.

Kernel: `long sum_to_n(long n) = 1+2+...+n`  (the loop example from the ASM-variations dialogue).

THE COMBINATORIAL OBJECT — what is synthesized / researched / composed — is ONLY the middle slots,
the asm pieces:
  • INIT — how the accumulator is zeroed   (xor / mov 0 / sub)                         [3 variants]
  • LOOP — how the sum loop is written      (down-counter+jnz / up-compare /
           hardware `loop` / unroll-by-2)                                              [4 variants]
  → 3 x 4 = 12 equivalent machine-code routines, all CONTRACT-PINNED (arg n in rdi, sum in rax,
    scratch rcx/rdx; no callee-saved register touched) so ANY combination is a valid leaf function.

HEAD and TAIL are the INVARIANT MEASUREMENT RIG — they do NOT vary; they only assemble the synthesized
asm, verify it against the reference, and time it on this host (then emit the K=V metrics). The whole
"combinatorial difference" lives in the middle; the ends just measure.

RunMeFirstOnce is the OBSERVER / ANALYZER: it profiles the current hardware + OS + toolchain (so the
optimum is annotated with the machine it is FOR) and observes each asm candidate arriving at the
Executor.

Runs on THIS machine (gcc + ctypes, x86-64). `--run` emits a bundle_run-ready spec + the RunMeFirstOnce
observer so the SAME space runs through the full Core->Reader->Executor->Analyzer chain.

  python3 asm_superopt.py          # observe hardware -> race all 12 variants here -> emit the run spec
  python3 asm_superopt.py --run    # just (re)emit the bundle_run spec + observer
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---- the combinatorial object: interchangeable ASM pieces (the MIDDLE slots) ----
INIT = {
    "xor":  "  xor rax, rax\n",
    "mov0": "  mov rax, 0\n",
    "sub":  "  sub rax, rax\n",
}
LOOP = {
    "downcount_jnz": "  mov rcx, rdi\n.Ld:\n  add rax, rcx\n  dec rcx\n  jnz .Ld\n",
    "upcount_cmp":   "  mov rcx, 1\n.Lu:\n  cmp rcx, rdi\n  jg .Eu\n  add rax, rcx\n  inc rcx\n  jmp .Lu\n.Eu:\n",
    "hw_loop":       "  mov rcx, rdi\n.Lh:\n  add rax, rcx\n  loop .Lh\n",
    "unroll2":       ("  mov rcx, rdi\n.L2:\n  cmp rcx, 2\n  jl .R2\n  add rax, rcx\n"
                      "  lea rdx, [rcx-1]\n  add rax, rdx\n  sub rcx, 2\n  jmp .L2\n"
                      ".R2:\n  test rcx, rcx\n  jz .E2\n  add rax, rcx\n.E2:\n"),
}
# invariant scaffold of the .s (the function shell)
ASM_HEAD = ".intel_syntax noprefix\n.globl sum_to_n\nsum_to_n:\n"
ASM_TAIL = "  ret\n"

N = 20_000_000                               # loop length for timing (sum fits int64)
REPS = 7                                     # best (least-noisy) of REPS timed calls
TEST_NS = (1, 2, 3, 10, 1000, 100000)        # correctness oracle inputs (n >= 1)


def _ref(n):
    return n * (n + 1) // 2


def build_asm(init_label, loop_label):
    return ASM_HEAD + INIT[init_label] + LOOP[loop_label] + ASM_TAIL


def assemble_and_measure(asm):
    """The MEASUREMENT RIG (what HEAD/TAIL do per candidate): assemble -> verify -> time on THIS CPU.
    Returns (assembled, correct, ns_total | None)."""
    d = tempfile.mkdtemp()
    s, so = os.path.join(d, "k.s"), os.path.join(d, "k.so")
    Path(s).write_text(asm)
    r = subprocess.run(["gcc", "-shared", "-fPIC", "-Wa,--noexecstack", "-O0", "-o", so, s],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, False, None
    lib = ctypes.CDLL(so)
    lib.sum_to_n.restype = ctypes.c_int64
    lib.sum_to_n.argtypes = [ctypes.c_int64]
    if not all(lib.sum_to_n(n) == _ref(n) for n in TEST_NS):
        return True, False, None
    lib.sum_to_n(N)                          # warm
    best = None
    for _ in range(REPS):
        t = time.perf_counter_ns(); lib.sum_to_n(N); e = time.perf_counter_ns() - t
        best = e if best is None or e < best else best
    return True, True, best


# ---- RunMeFirstOnce: the OBSERVER / hardware + OS + toolchain analyzer ----
def observe_hardware():
    def cpu():
        try:
            for ln in Path("/proc/cpuinfo").read_text().splitlines():
                if ln.startswith("model name"):
                    return ln.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.processor() or "unknown"

    def ver(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0]
        except Exception:
            return "n/a"

    return {"cpu": cpu(), "arch": platform.machine(), "logical_cores": os.cpu_count(),
            "os": f"{platform.system()} {platform.release()}",
            "gcc": ver(["gcc", "--version"]), "as": ver(["as", "--version"]),
            "python": platform.python_version()}


# the standalone observer the Reader hands to the Executor (run per candidate, non-fatal)
RUNME = (
    "import os, platform, subprocess, sys\n"
    "def v(c):\n"
    "    try: return subprocess.run(c, capture_output=True, text=True).stdout.splitlines()[0]\n"
    "    except Exception: return 'n/a'\n"
    "cpu = 'unknown'\n"
    "try:\n"
    "    for ln in open('/proc/cpuinfo'):\n"
    "        if ln.startswith('model name'): cpu = ln.split(':',1)[1].strip(); break\n"
    "except Exception: pass\n"
    "cand = os.path.basename(sys.argv[1]) if len(sys.argv) > 1 else '-'\n"
    "print('[RunMeFirstOnce] optimizing FOR: %s | %s | cores %s | %s %s | %s | observing asm candidate %s'\n"
    "      % (cpu, platform.machine(), os.cpu_count(), platform.system(), platform.release(), v(['gcc','--version']), cand))\n"
)

# the per-candidate measurement rig embedded in TAIL (assemble + verify + time + emit K=V)
_TAIL = (
    "ASM += '  ret\\n'\n"
    "_d = tempfile.mkdtemp(); _s = os.path.join(_d, 'k.s'); _so = os.path.join(_d, 'k.so')\n"
    "open(_s, 'w').write(ASM)\n"
    "_r = subprocess.run(['gcc','-shared','-fPIC','-Wa,--noexecstack','-O0','-o',_so,_s], capture_output=True, text=True)\n"
    "def _ref(n): return n*(n+1)//2\n"
    "if _r.returncode != 0:\n"
    "    FW_VAR = 3; print('app=asm_superopt assembled=0 correct=0 ns_total=0 FW_VAR=3')\n"
    "else:\n"
    "    _lib = ctypes.CDLL(_so); _lib.sum_to_n.restype = ctypes.c_int64; _lib.sum_to_n.argtypes = [ctypes.c_int64]\n"
    "    if not all(_lib.sum_to_n(_n) == _ref(_n) for _n in (1,2,3,10,1000,100000)):\n"
    "        FW_VAR = 2; print('app=asm_superopt assembled=1 correct=0 ns_total=0 FW_VAR=2')\n"
    "    else:\n"
    "        _N = 20000000; _lib.sum_to_n(_N); _best = None\n"
    "        for _ in range(7):\n"
    "            _t = time.perf_counter_ns(); _lib.sum_to_n(_N); _e = time.perf_counter_ns() - _t\n"
    "            _best = _e if _best is None or _e < _best else _best\n"
    "        FW_VAR = 0\n"
    "        print('app=asm_superopt assembled=1 correct=1 ns_total=%d ns_per_elem=%.4f FW_VAR=0' % (_best, _best/_N))\n"
)
_HEAD = ("import ctypes, subprocess, tempfile, os, time\n"
         "ASM = '.intel_syntax noprefix\\n.globl sum_to_n\\nsum_to_n:\\n'\n")


def emit_run_toml(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def raw_slot(sheet, frags):
        L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
             'verb  = "FW_Combi(1)"', 'raw   = true', 'values = [']
        for f in frags:
            body = f if f.startswith("\n") else "\n" + f
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        return L + [']', '']

    inits = [f"ASM += {INIT[k]!r}\n" for k in INIT]      # -> ASM += '  xor rax, rax\n'
    loops = [f"ASM += {LOOP[k]!r}\n" for k in LOOP]
    L = ['title = "ASM superoptimization (RUN) — fastest correct sum_to_n for THIS hardware, full Bundle"',
         'note  = "Middle slots INIT x LOOP = the combinatorial asm object; HEAD/TAIL assemble+verify+time '
         'on the host; RunMeFirstOnce observes the hardware/OS. FW_VAR=0 iff correct; Analyzer ns_total:min '
         'picks the hardware-optimal variant."',
         'args = ["kernel=sum_to_n", "metric=ns_total_min", "target=this_host"]',
         "runme = '''\n" + RUNME + "'''", '',
         '[[goals]]', 'key = "ns_total"', 'dir = "min"',
         '[[goals]]', 'key = "correct"', 'dir = "max"', '']
    L += raw_slot("HEAD", [_HEAD])
    L += raw_slot("INIT", inits)
    L += raw_slot("LOOP", loops)
    L += raw_slot("TAIL", [_TAIL])
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "asm computed the wrong sum"',
          '[[custom_vars]]', 'code = 3', 'msg  = "asm did not assemble"', '']
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    (path.parent / "runmefirstonce.first").write_text(RUNME, encoding="utf-8")
    print(f"  RUN spec -> {path}  ({len(inits) * len(loops)} asm candidates; runme = hardware observer)")


def main():
    if "--run" in sys.argv[1:]:
        a = [x for x in sys.argv[1:] if not x.startswith("--")]
        emit_run_toml(Path(a[0]) if a else
                      Path(__file__).resolve().parent / "run" / "asm_superopt" / "asm_superopt.toml")
        return

    print("=== ASM superoptimization (combinatorial program building) — on THIS hardware ===\n")
    hw = observe_hardware()
    print("[RunMeFirstOnce] observer — optimizing FOR:")
    for k, v in hw.items():
        print(f"    {k:<14}{v}")
    n_var = len(INIT) * len(LOOP)
    print(f"\n  kernel: long sum_to_n(long n) = 1+..+n   |   combinatorial object = "
          f"INIT({len(INIT)}) x LOOP({len(LOOP)}) = {n_var} asm variants")
    print("  HEAD/TAIL = invariant rig (assemble + verify + time on this CPU); only the middle asm pieces vary.\n")

    rows = []
    for il in INIT:
        for ll in LOOP:
            asm_ok, correct, ns = assemble_and_measure(build_asm(il, ll))
            rows.append((il, ll, asm_ok, correct, ns))

    print(f"    {'INIT':<6}{'LOOP':<16}{'ok':>3}{'ns_total':>14}{'ns/elem':>11}")
    for il, ll, asm_ok, correct, ns in sorted(rows, key=lambda r: (r[4] is None, r[4] or 0)):
        if correct:
            tail = f"{ns:>14,}{ns / N:>11.4f}"
        else:
            tail = f"{('(assemble fail)' if not asm_ok else '(WRONG)'):>25}"
        print(f"    {il:<6}{ll:<16}{('Y' if correct else 'n'):>3}{tail}")

    correct_rows = sorted([r for r in rows if r[3]], key=lambda r: r[4])
    if correct_rows:
        fil, fll, _, _, fns = correct_rows[0]
        sil, sll, _, _, sns = correct_rows[-1]
        print(f"\n  *** FASTEST CORRECT on this CPU: INIT={fil} + LOOP={fll}  "
              f"({fns / N:.4f} ns/elem) ***")
        print(f"      slowest correct: INIT={sil} + LOOP={sll}  ({sns / N:.4f} ns/elem) "
              f"-> {sns / fns:.2f}x slower")
        print(f"      K=V -> fastest=INIT_{fil}+LOOP_{fll} ns_total={fns} ns_per_elem={fns / N:.4f} correct=1")

    emit_run_toml(Path(__file__).resolve().parent / "run" / "asm_superopt" / "asm_superopt.toml")
    print(f"\n  -> the engine bred {n_var} machine-code routines, ran each on real silicon, and the "
          f"verdict picked the fastest CORRECT one FOR THIS CPU (not a guess — measured).")


if __name__ == "__main__":
    main()
