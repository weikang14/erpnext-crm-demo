# Technology Stack (manifest-verified)

| Piece | Version | Evidence |
|---|---|---|
| CRM Python | 3.13 (3.13.16 in container) | `CRM/Dockerfile:1` `FROM python:3.13-slim` |
| CRM Django | 6.1.1 | `CRM/requirements.txt:1` |
| CRM gunicorn | 26.2.0, `--workers 2 --worker-class gthread --threads 4`, **no `--timeout`, so the 30 s default applies** | `CRM/requirements.txt:2`, `CRM/Dockerfile:12` |
| CRM DB driver | psycopg[binary] 3.3.6 | `CRM/requirements.txt:3` |
| CRM static | whitenoise 6.12.0 | `CRM/requirements.txt:4` |
| CRM DB | PostgreSQL 17-alpine | `CRM/docker-compose.yml:6` |
| **CRM HTTP client** | **none installed** (`pip list` in `web`); stdlib `urllib` is available | `CRM/requirements.txt` (4 lines) |
| ERPNext | image `frappe/erpnext:v16.37.0`; running erpnext 16.37.0, frappe 16.36.1 | `ERP/Dockerfile:1`; `bench version` (erp chunk) |
| ombak_mfg | 0.0.1, Python >=3.14, ruff, tabs, line length 110 | `ERP/apps/ombak_mfg/pyproject.toml` |
| ERP DB / cache | mariadb 11.8, redis 6.2-alpine | `ERP/docker-compose.yml:150,169,176` |
| Portal | Python 3.13-slim, Django 6.1.1, **requests 2.34.2**, gunicorn 26.2.0 | `ERP/portal/Dockerfile`, `ERP/portal/requirements.txt` |
| Docker | Docker Desktop 27.3.1, Compose v2.29.7-desktop.1 | `docker info`, `docker compose version` (erp chunk) |

What this means for 004:
- Adding a dependency to `CRM/requirements.txt` needs `docker compose up -d --build`. The code is bind-mounted (`CRM/docker-compose.yml:30`), but the packages are baked into the image.
- A new CRM dependency should pin `requests==2.34.2` to match the portal. Stdlib `urllib` avoids the new dependency, but there is no in-repo precedent for it.
- There is no job runner in the CRM: no celery, cron or scheduler. The container runs only gunicorn (`CRM/Dockerfile:12`).
