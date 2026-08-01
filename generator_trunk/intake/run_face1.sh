#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Launch the Face 1 app the RIGHT way: serve it from the real engine and open
# it in your browser. When the page is SERVED (not opened as a file://), the Run
# button just fires the whole Bundle pipeline directly — no OS dialogs, no
# "choose an application", nothing to register. This is the reliable path.
#
#   bash intake/run_face1.sh            # or double-click it in your file manager
#
# Ctrl-C in this window stops the engine.
# ---------------------------------------------------------------------------
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # generator_trunk (holds bundle_run.py)

# serve_face1.py imports the bundle package from the repo root.
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$ROOT"

# Reader/Core JARs need a Java 25 runtime (class 69) on PATH, else real runs fail.
for j in /usr/lib/jvm/jdk-25*/bin /usr/lib/jvm/*25*/bin; do
  if [ -d "$j" ]; then export PATH="$j:$PATH"; break; fi
done

cd "$ROOT" || exit 1
echo "Starting the Combinatorics Framework engine + UI…"
echo "(the page will open in your browser; press Run there to fire the real pipeline)"
exec python3 intake/serve_face1.py "$@"      # opens the served UI via webbrowser.open
