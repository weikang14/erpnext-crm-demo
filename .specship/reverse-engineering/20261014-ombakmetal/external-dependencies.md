# External Dependencies

## ERPNext, as seen from the CRM (new for 004)
| Item | Today | Evidence |
|---|---|---|
| Reachability | The CRM `web` container is on `ombak-crm_default` only. `backend`, `erp-backend-1` and `erp-frontend-1` **do not resolve**. `host.docker.internal` (192.168.65.254) on `:8080` answers `GET /api/method/ping` with 200 `{"message":"pong"}` | `CRM/docker-compose.yml` (no `networks:`); probes from `ombak-crm-web-1` (both chunks) |
| Site routing | Frappe picks the site from `X-Frappe-Site-Name`, then Host (`frappe/app.py:215`). The `:8080` nginx **forces** `localhost`, so any write via `:8080` hits the demo data. Only `backend:8000` honours Host | `ERP/docker-compose.yml:88` (`FRAPPE_SITE_NAME_HEADER: localhost`) |
| ERP network | `erp_frappe_network` (172.18.0.0/16). Its name derives from project `erp` + `frappe_network`, with **no `name:` pin** | `ERP/docker-compose.yml:187-189` |
| Credentials pattern | The site config holds `<x>_api_key`/`<x>_api_secret`, set by compose `create-site` and copied onto the API user by `setup_masters` | `ERP/docker-compose.yml:54-58`, `masters.py:522-527` |
| Existing API user | `shopfloor.terminal@ombakmetal.example`, role `Shop Floor Terminal`. Its key gets **403 on GET Sales Order** (live). It must not be reused | `masters.py:124-135`; erp chunk |

## Env vars
- The CRM has `DJANGO_SECRET_KEY`, `POSTGRES_HOST/DB/USER/PASSWORD` and `DEMO_PASSWORD`, with host overrides `CRM_SECRET_KEY`, `CRM_DB_PASSWORD` and `CRM_DEMO_PASSWORD` (`CRM/docker-compose.yml:22-28`). Settings also read `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` and `POSTGRES_TEST_DB` (`CRM/crm/settings.py:10-12,72`). **There are no `ERPNEXT_*` vars yet.**
- The portal precedent is `ERPNEXT_URL` (default `http://backend:8000`), `ERPNEXT_SITE` (`localhost`), `ERPNEXT_API_KEY`, `ERPNEXT_API_SECRET`, plus the constant `ERPNEXT_TIMEOUT = 10` (`ERP/portal/portal/settings.py:15-19`). Compose fills the key and secret from `SHOPFLOOR_API_KEY/SECRET` with the demo defaults `shopfloor-demo-key`/`-secret` (`ERP/docker-compose.yml:138-141`). There is no `ERP/.env`.

## Timeouts
CRM gunicorn uses the default 30 s (`CRM/Dockerfile:12`); the portal client uses 10 s. Any ERPNext call inside a CRM request needs a timeout well under 30 s.
