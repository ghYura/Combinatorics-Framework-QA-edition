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

# ---------------------------------------------------------------------------
# One-time setup: register the `combframework://` URL scheme so the Face 1 page
# can start its own backend. A browser page cannot spawn a process from nothing
# (sandbox), but it CAN hand a registered scheme to the OS — this wires that up.
#
#   bash intake/install_launcher.sh      # run once
#
# After this, opening face1.html as a file:// page and pressing "Start the
# engine" launches serve_face1.py by itself and drops you into the real app.
# ---------------------------------------------------------------------------
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$HERE/engine_launcher.sh"
chmod +x "$LAUNCHER" 2>/dev/null || true

APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPDIR"
DESKTOP="$APPDIR/combframework-engine.desktop"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Combinatorics Framework Engine
Comment=Starts the Face 1 real backend (serve_face1.py)
Exec="$LAUNCHER" %u
Terminal=false
NoDisplay=true
MimeType=x-scheme-handler/combframework;
EOF
chmod +x "$DESKTOP" 2>/dev/null || true

update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
xdg-mime default combframework-engine.desktop x-scheme-handler/combframework >/dev/null 2>&1 || true

echo "✓ Registered  combframework://  ->  $LAUNCHER"
if command -v xdg-mime >/dev/null 2>&1; then
  echo "  handler: $(xdg-mime query default x-scheme-handler/combframework 2>/dev/null || echo '(query unavailable)')"
fi
echo "  The Face 1 page's \"Start the engine\" button now launches the backend by itself."
