═══════════════════════════════════════════════════════════════════════
 Code-piece variants of AnalyzerCore.java for combinatorial gluing
═══════════════════════════════════════════════════════════════════════

Layout convention
─────────────────
  head.txt          imports + class skeleton + regex constants +
                    global Metrics struct (40 fields, 10 pieces × 4)
  tail.txt          main() that exercises the glued program, prints
                    metrics in 'key=value' form to stdout, AND writes
                    them to a unique file under /tmp/ whose path is
                    also printed.

  N.txt             "initial" piece — original AnalyzerCore code,
                    contract-preserving, instrumented with metrics.
  N_M.txt           variant M of piece N. Same public signature;
                    different internal realization, same metric
                    instrumentation.

The combinatorics engine glues:
    head.txt + (one of {N.txt, N_1.txt, N_2.txt, …}) for each N + tail.txt
into a single Java source, compiles + runs it. Each run emits its own
metrics file under /tmp/. The Analyzer (this project) ingests those
metric files and applies the optimisation-theory toolkit (Brent /
Newton / Nelder-Mead / SA / Simpson / RK4 / Pareto) to find the
dominant combination.

Pieces (10 total; 30 variant files)
───────────────────────────────────
  cool-down (small surface, easy variants)
  ──────────────────────────────────────────
  1  mean(List<Double>)              initial / Kahan / parallel-stream
  2  charEntropy(String)             initial / pure HashMap / UTF-8 byte
  3  compressSignature(String)       initial / regex-collapse / ASCII-LUT
  4  canonicalNumber(double)         initial / BigDecimal / DecimalFormat
  5  isShellCommandComplete(String)  initial / simplified / regex-only

  HOT path (called once per analysed line — dominant cost)
  ───────────────────────────────────────────────────────
  6  tokenLowers(List<String>)       initial / ArrayList loop /
                                     ASCII fast-path with bit-OR
                                     (sub-piece of extractFeatures)
  7  isHighFreqToken(String, List, Map, int)
                                     initial / per-call HashSet /
                                     identity-keyed WeakHashMap cache
                                     (sub-piece of scoreLine inner loop;
                                      this is where O(N×M) comes from)
  8  extractNumbers(String)          initial regex while-find /
                                     Matcher.results stream / hand-rolled
                                     scanner (no regex)
                                     (sub-piece of extractFeatures)
  9  lineKind(...)                   if/else cascade / packed-bitmap
                                     dispatch / predicate-priority list
                                     (sub-piece of extractFeatures)
 10  delimiterCounts(String)         initial String.indexOf / boolean[128]
                                     LUT / int[128] histogram + lazy
                                     materialisation
                                     (sub-piece of extractFeatures)

Search space
────────────
  Pieces 1-5: 3 implementations each = 3⁵   =   243 programs
  Pieces 6-10: 3 implementations each = 3⁵   =   243 programs
  Combined:   3¹⁰                            = 59 049 programs
  the engine can synthesise from this folder.

  File count: 30 piece variants + head.txt + tail.txt = 32 glue inputs;
  this README is the 33rd .txt file in the directory.

Metric naming convention
────────────────────────
  pN_invocations          — # of times the piece was called
  pN_duration_ns          — total nanoseconds spent inside the piece
  pN_total_input_*        — accumulated input size
  pN_total_output_*       — accumulated output size, where applicable
  (pN_match_count, pN_completed_count, pN_kv_numeric_count, … for the
   pieces that have a meaningful boolean / count outcome)

All metric NAMES are UNIFIED across siblings (1.txt, 1_1.txt, 1_2.txt
all measure the same `p1_*` set). Metric names VARY across distinct
initial pieces (`p1_*` vs `p2_*` vs …) so a glued program emits a
unique row of values that identify which piece-variant produced what.

How to glue & run by hand
─────────────────────────
  cat head.txt 1.txt 2.txt 3.txt 4.txt 5.txt 6.txt 7.txt 8.txt 9.txt 10.txt tail.txt \
      > /tmp/glue_test/generated/Generated.java
  cd /tmp/glue_test && javac generated/Generated.java && java generated.Generated

  Each piece-N can independently be replaced by any N_K.txt to produce
  one of the 59 049 distinct programs.
