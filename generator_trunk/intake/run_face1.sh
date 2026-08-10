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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

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
