#!/usr/bin/env bash
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

echo "── Running AllVerifiersRunner from $JAR ──"
exec java -cp "$JAR" com.yurii.analyzer.AllVerifiersRunner "$@"
