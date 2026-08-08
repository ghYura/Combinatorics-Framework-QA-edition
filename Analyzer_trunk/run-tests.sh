#!/usr/bin/env bash
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

#
# Canonical regression check for the heuristic analyzer.
#
# Why a shell script and not `mvn test`:
#   The verifier drivers are executable main classes rather than JUnit tests.
#   The shaded JAR produced by `mvn package` already contains those classes
#   and their runtime dependencies, so no dependency-plugin resolution is
#   needed to assemble a second classpath.
#
# Usage:
#   ./run-tests.sh              # runs the full suite
#   mvn package && ./run-tests.sh   # full rebuild + verify
#
# Exits 0 on success, non-zero on any failure.

set -euo pipefail
cd "$(dirname "$0")"

find_shaded_jar() {
    local candidates newest candidate
    shopt -s nullglob
    candidates=(target/heuristic-analyzer-flatlaf-*.jar)
    shopt -u nullglob
    ((${#candidates[@]})) || return 1

    newest="${candidates[0]}"
    for candidate in "${candidates[@]:1}"; do
        [[ "$candidate" -nt "$newest" ]] && newest="$candidate"
    done
    printf '%s\n' "$newest"
}

JAR="$(find_shaded_jar || true)"
REBUILD_REASON=""
if [[ -z "$JAR" ]]; then
    REBUILD_REASON="missing"
elif [[ -n "$(find pom.xml src/main -type f -newer "$JAR" -print -quit)" ]]; then
    REBUILD_REASON="stale"
fi

if [[ -n "$REBUILD_REASON" ]]; then
    echo "── Building shaded Analyzer JAR (offline: $REBUILD_REASON) ──"
    mvn -o -q -DskipTests package
    JAR="$(find_shaded_jar || true)"
fi

if [[ -z "$JAR" || ! -f "$JAR" ]]; then
    echo "ERROR: Maven package did not produce target/heuristic-analyzer-flatlaf-*.jar" >&2
    exit 2
fi

# SortMockupRun is the one driver that needs an input corpus: a file whose every
# line is an executable command emitting agnostic metrics. It used to be an
# unversioned local file, so a clean checkout always reported
# `SKIP (input file not present)` and the driver never ran. The corpus is
# runtime output and must not be committed, so generate it into a temporary
# directory from its checked-in generator and delete it again on exit. An
# operator who exports ANALYZER_SORT_CORPUS keeps full control and we touch
# nothing.
CORPUS_TMPDIR=""
cleanup() {
    [[ -n "$CORPUS_TMPDIR" && -d "$CORPUS_TMPDIR" ]] && rm -rf "$CORPUS_TMPDIR"
    return 0
}
trap cleanup EXIT

if [[ -z "${ANALYZER_SORT_CORPUS:-}" ]]; then
    if CORPUS_TMPDIR="$(mktemp -d)"; then
        if python3 samples/make_sort_corpus.py "$CORPUS_TMPDIR/sort_corpus.txt" >/dev/null 2>&1; then
            export ANALYZER_SORT_CORPUS="$CORPUS_TMPDIR/sort_corpus.txt"
        else
            echo "NOTE: could not generate the sort corpus (python3 unavailable?)," >&2
            echo "      SortMockupRun will self-skip." >&2
            rm -rf "$CORPUS_TMPDIR"; CORPUS_TMPDIR=""
        fi
    else
        CORPUS_TMPDIR=""
    fi
fi

echo "── Running AllVerifiersRunner from $JAR ──"
java -cp "$JAR" com.yurii.analyzer.AllVerifiersRunner "$@"
