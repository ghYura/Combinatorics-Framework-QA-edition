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
# combframework:// protocol target — lets the Face 1 page start its own backend.
#
# Registered once by install_launcher.sh. When the file:// page's "Start the
# engine" button navigates to `combframework://start`, the OS runs this script:
# it brings up serve_face1.py (the real bundle_run.py backend) on 127.0.0.1:PORT
# if it isn't already listening, then exits. The page polls /api/ping and
# redirects itself to the served app. Nothing here opens a browser — the page
# that triggered us does the navigation.
# ---------------------------------------------------------------------------
PORT="${COMBFRAMEWORK_PORT:-8765}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # generator_trunk (holds bundle_run.py)
LOG="/tmp/combframework_engine_${PORT}.log"

# Already serving? Then there is nothing to start.
if command -v curl >/dev/null 2>&1 \
   && curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/api/ping"; then
  exit 0
fi

# serve_face1.py imports the `bundle` package from the repo root.
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$ROOT"

# Reader/Core JARs need a Java 25 runtime (class 69). Put one on PATH if present.
for j in /usr/lib/jvm/jdk-25*/bin /usr/lib/jvm/*25*/bin; do
  if [ -d "$j" ]; then export PATH="$j:$PATH"; break; fi
done

cd "$ROOT" || exit 1

# Fully detach so the server outlives this short-lived handler process.
if command -v setsid >/dev/null 2>&1; then
  setsid python3 intake/serve_face1.py --no-browser --port "$PORT" >"$LOG" 2>&1 < /dev/null &
else
  nohup python3 intake/serve_face1.py --no-browser --port "$PORT" >"$LOG" 2>&1 < /dev/null &
  disown 2>/dev/null || true
fi
exit 0
