#!/usr/bin/env bash
# Live contract tests (004): the CRM's real ERPNext client against the ERP stack's contract.localhost site, in a
# one-off web container on the ERP link network (the running web container is not touched). They create customers
# and submitted sales orders, so they never run on the demo site localhost.
# Needs both stacks up (ERP/ and CRM/). Usage: bash CRM/scripts/test-erp.sh [manage.py test args]
set -euo pipefail
site="${ERPNEXT_SITE:-contract.localhost}"
if [ "$site" != contract.localhost ]; then
  echo "test-erp.sh writes to ERPNext: it runs on contract.localhost only, not '$site'." >&2
  exit 1
fi
cd "$(dirname "$0")/../../ERP"
# the ERP compose reads ERP/.env; read it here too, so both sides use the same CRM key
if [ -f .env ]; then set -a; . ./.env; set +a; fi
key="${CRM_API_KEY:-crm-demo-key}"
secret="${CRM_API_SECRET:-crm-demo-secret}"

docker compose exec -T -e CRM_API_KEY="$key" -e CRM_API_SECRET="$secret" backend bash -c '
set -e
if [ ! -d sites/contract.localhost ]; then
  bench new-site contract.localhost --mariadb-user-host-login-scope="%" --admin-password=admin \
    --db-root-username=root --db-root-password=admin --install-app erpnext --install-app ombak_mfg >/dev/null
fi
bench --site contract.localhost set-config crm_api_key "$CRM_API_KEY"
bench --site contract.localhost set-config crm_api_secret "$CRM_API_SECRET"
bench --site contract.localhost migrate --skip-search-index >/dev/null
bench --site contract.localhost execute ombak_mfg.setup.masters.setup_masters >/dev/null
# CT-12: a customer the CRM did not create, its address owned by Administrator (as on the demo site)
bench --site contract.localhost execute ombak_mfg.setup.contract.existing_customer >/dev/null
'
# CT-13: a draft and a submitted order Administrator created, which the CRM key must not read, find or change
others=$(docker compose exec -T backend bench --site contract.localhost execute ombak_mfg.setup.contract.others_orders | tail -1)

cd ../CRM
docker compose -f docker-compose.yml -f docker-compose.erp.yml run --rm --no-deps -e ERPNEXT_SITE="$site" \
  -e ERPNEXT_API_KEY="$key" -e ERPNEXT_API_SECRET="$secret" -e ERP_CONTRACT=1 -e POSTGRES_TEST_DB=test_crm_contract \
  -e ERP_OTHERS_ORDERS="$others" web python manage.py test --noinput "${@:-sales.tests.test_erp_contract}"

# BRT-20: a submitted CRM order is not planned on its own (no Work Order or Production Plan references one)
cd ../ERP
sql='select count(*) from `tabSales Order` so where so.crm_reference is not null and (exists (select 1'
sql="$sql from \`tabWork Order\` w where w.sales_order = so.name) or exists (select 1"
sql="$sql from \`tabProduction Plan Sales Order\` p where p.sales_order = so.name))"
planned=$(docker compose exec -T backend bench --site contract.localhost execute frappe.db.sql --args "[\"$sql\"]")
if [ "$(echo "$planned" | tail -1)" != "[[0]]" ]; then
  echo "BRT-20: CRM orders were planned on their own: $planned" >&2
  exit 1
fi
echo "BRT-20 OK: no Work Order or Production Plan references a CRM order"

# AC21: the CRM container reaches the ERP backend only, never its Redis, MariaDB or other services, by name or by IP
targets="redis-queue:6379 redis-cache:6379 db:3306"
for s in db:3306 redis-queue:6379 redis-cache:6379 frontend:8080 portal:8000; do
  id=$(docker compose ps -q "${s%:*}")
  for host in $(docker inspect -f '{{.Name}} {{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$id"); do
    targets="$targets ${host#/}:${s#*:}"
  done
done
cd ../CRM
docker compose -f docker-compose.yml -f docker-compose.erp.yml run --rm --no-deps -T -e ERPNEXT_SITE="$site" \
  -e ERP_TARGETS="$targets" web python - <<'PY'
import json, os, socket, struct, sys, urllib.request

def opens(target):
    host, port = target.rsplit(":", 1)
    try:
        socket.create_connection((host, int(port)), timeout=3).close()
        return True
    except OSError:  # the name does not resolve, or the connection is refused or times out
        return False

leaks = [t for t in os.environ["ERP_TARGETS"].split() if opens(t)]
if leaks:
    sys.exit(f"AC21: the CRM container reaches ERP internals: {' '.join(leaks)}")
ping = urllib.request.Request("http://backend:8000/api/method/ping", headers={"Host": os.environ["ERPNEXT_SITE"]})
if json.load(urllib.request.urlopen(ping, timeout=10)).get("message") != "pong":
    sys.exit("AC21: backend:8000 did not answer ping")
with socket.create_connection(("db", 5432), timeout=3) as pg:  # PostgreSQL answers an SSLRequest with S or N
    pg.sendall(struct.pack("!ii", 8, 80877103))
    if pg.recv(1) not in (b"S", b"N"):
        sys.exit("AC21: db:5432 is not the CRM PostgreSQL")
print(f"AC21 OK: backend:8000 and the CRM db answer; unreachable: {os.environ['ERP_TARGETS']}")
PY
