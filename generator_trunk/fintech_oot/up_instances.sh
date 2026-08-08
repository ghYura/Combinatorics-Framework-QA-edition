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

# Bring up the TWO connected simulator instances that the Bundle batches target.
# Run this BEFORE `python3 ../bundle_run.py fintech_oot/batches/<batch>`.
#
#   bash fintech_oot/up_instances.sh        # launches both, stays in foreground
#
# The batch harness drives this live cluster over signed HTTP (HMAC enforcement +
# cross-node connectivity) while running the deep param/factor combinatorics
# in-process. Secret + ports must match the harness HEAD (OOT_SECRET / 8121 / 8122).
set -e
REG="${FINANCE_STACK_REGISTRY:-/tmp/fs_oot_reg}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
SUT_ROOT="${BUNDLE_SUT_ROOT:-$REPO_ROOT/suts}"
if [[ "$SUT_ROOT" != /* ]]; then
    SUT_ROOT="$REPO_ROOT/$SUT_ROOT"
fi
SIM="${SIM_DIR:-$SUT_ROOT/fin_tech_to_test}"
SECRET="${OOT_SECRET:-oot-secret}"

rm -rf "$REG"; mkdir -p "$REG"
export APP_SHARED_SECRET="$SECRET" FINANCE_STACK_REGISTRY="$REG" \
       PEER_PING_INTERVAL_SECONDS=2 PEER_RECONNECT_DELAY_SECONDS=1 PEER_UNAVAILABLE_AFTER_SECONDS=30
cd "$SIM"
python3 -m finance_stack.node --bank AURUM --alias toBank1 --port 8121 &
python3 -m finance_stack.node --bank NORD  --alias toBank2 --port 8122 &
echo "launched toBank1/AURUM :8121  <->  toBank2/NORD :8122   (secret=$SECRET, registry=$REG)"
echo "verify:  curl -s http://127.0.0.1:8121/health   (peers should show toBank2: AVAILABLE)"
wait
