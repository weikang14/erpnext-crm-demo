#!/usr/bin/env bash
# Run the ombak_mfg test suite on a separate site so tests never touch the demo data.
# Usage (from ERP/): bash scripts/test.sh [extra run-tests args, e.g. --module ombak_mfg.tests.test_alert]
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose exec -T backend bash -c '
if [ ! -d sites/test.localhost ]; then
  bench new-site test.localhost --mariadb-user-host-login-scope="%" --admin-password=admin \
    --db-root-username=root --db-root-password=admin --install-app erpnext --install-app ombak_mfg
  bench --site test.localhost set-config allow_tests true
fi
bench --site test.localhost migrate --skip-search-index >/dev/null
'
docker compose exec -T backend bench --site test.localhost run-tests --app ombak_mfg "$@"
