# SPDX-License-Identifier: BUSL-1.1
# Environment for the small use-case demos. Copy to bundle_env.sh (git-ignored), set your own values, then:
#   source SmallUseCasesDemo/bundle_env.sh
_DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BUNDLE_SCRATCH_ROOT="$_DEMO_DIR/_work"
export BUNDLE_MAIN_DB_HOST=127.0.0.1 BUNDLE_MAIN_DB_PORT=5433 BUNDLE_MAIN_DB_USER=postgres BUNDLE_MAIN_DB_PASSWORD=change-me
export BUNDLE_RESULTS_DB_HOST=127.0.0.1 BUNDLE_RESULTS_DB_PORT=5432 BUNDLE_RESULTS_DB_USER=postgres BUNDLE_RESULTS_DB_PASSWORD=change-me
export PYTHONDONTWRITEBYTECODE=1
# The Framework's virtual environment (see the top-level README):
source "$_DEMO_DIR/../.venv/bin/activate"
