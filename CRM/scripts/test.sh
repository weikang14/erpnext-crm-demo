#!/usr/bin/env bash
# Run the CRM test suite in the web container (Django TestCase on PostgreSQL). Args (test labels, flags) replace the default label "sales".
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --wait db web >/dev/null
docker compose exec -T web python manage.py test --noinput "${@:-sales}"
