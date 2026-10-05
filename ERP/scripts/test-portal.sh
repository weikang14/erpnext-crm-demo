#!/usr/bin/env bash
# Run the Django terminal's tests: unit tests plus contract tests against the real ERPNext
# contract.localhost site. Usage (from ERP/): bash scripts/test-portal.sh [manage.py test args]
set -euo pipefail
cd "$(dirname "$0")/.."
# docker compose reads ERP/.env; read it here too so a custom API key reaches the backend shell
if [ -f .env ]; then set -a; . ./.env; set +a; fi

# pass the same key/secret the portal uses (compose reads ERP/.env) into the backend shell
docker compose exec -T -e SHOPFLOOR_API_KEY="${SHOPFLOOR_API_KEY:-shopfloor-demo-key}"   -e SHOPFLOOR_API_SECRET="${SHOPFLOOR_API_SECRET:-shopfloor-demo-secret}" backend bash -c '
if [ ! -d sites/contract.localhost ]; then
  bench new-site contract.localhost --mariadb-user-host-login-scope="%" --admin-password=admin \
    --db-root-username=root --db-root-password=admin --install-app erpnext --install-app ombak_mfg >/dev/null
fi
bench --site contract.localhost set-config shopfloor_api_key "${SHOPFLOOR_API_KEY:-shopfloor-demo-key}"
bench --site contract.localhost set-config shopfloor_api_secret "${SHOPFLOOR_API_SECRET:-shopfloor-demo-secret}"
bench --site contract.localhost migrate --skip-search-index >/dev/null
bench --site contract.localhost execute ombak_mfg.setup.masters.setup_masters >/dev/null
'
fixture=$(docker compose exec -T backend bench --site contract.localhost execute ombak_mfg.setup.contract.fresh_job_cards | tail -1)
docker compose exec -T -e CONTRACT_SITE=contract.localhost -e CONTRACT_FIXTURE="$fixture" portal \
  python manage.py test terminal "$@"
