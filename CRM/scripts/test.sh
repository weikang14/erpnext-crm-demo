#!/usr/bin/env bash
# Run the CRM test suite in the web container (Django TestCase on PostgreSQL). Args (test labels, flags) replace the default label "sales".
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "$(docker compose ps -q --status running web)" ]; then
  # web is already up, maybe with the ERPNext link (docker-compose.erp.yml): don't recreate it without the link
  docker compose up -d --wait db >/dev/null
else
  docker compose up -d --wait db web >/dev/null
fi
docker compose exec -T web python manage.py test --noinput "${@:-sales}"
