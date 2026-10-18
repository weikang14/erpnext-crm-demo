# Repo Map (mission 004 scope)

HEAD `b90682a` on `main`, 2026-10-14. `git ls-files` has 236 tracked files: `CRM/` 91, `ERP/` 125, `.specship/` 16, plus the root `README.md`, `CHANGELOG.md`, `.gitignore` and `.gitattributes`.

One git repo holds two Docker Compose projects. Today they share no network and make no calls to each other.

| Area | What it is | Entrypoint / deploy | Port (host) |
|---|---|---|---|
| `CRM/` | Django 6.1 sales CRM (mission 003), app `sales`, project `crm` | `CRM/docker-compose.yml` (project `ombak-crm`: `db` + `web`); `CRM/Dockerfile:12` runs migrate, then createcachetable, then gunicorn | `127.0.0.1:8082` (`CRM/docker-compose.yml:35`) |
| `ERP/` | ERPNext v16 bench with the custom app `ombak_mfg` (001) and the Django shop-floor `portal` (002) | `ERP/docker-compose.yml` (project `erp`; network `frappe_network`, `:187-189`) | frontend nginx `127.0.0.1:8080`, portal `127.0.0.1:8081` (crm chunk, `docker ps`) |
| `ERP/apps/ombak_mfg/` | Frappe app: masters/demo setup, Defect Log doctypes, 4 reports, daily overdue alert | `hooks.py:267` (`before_tests`), `:269` (`scheduler_events`) | n/a |
| `ERP/portal/` | Django app that calls ERPNext over REST v2. **This is the integration pattern to copy.** | `ERP/portal/terminal/erpnext.py` | `:8081` |
| `.specship/` | SpecShip state, the archived missions 001-003, and this recon | `.specship/state.json` (mission 004, phase plan/recon) | n/a |

ERPNext sites on the bench (erp chunk, `ls sites`): `localhost` is the **demo**; `test.localhost` is used by `ERP/scripts/test.sh`; `contract.localhost` is used by `ERP/scripts/test-portal.sh`.

Mission 004 spans both areas. On the CRM side it touches the Won flow, the models and a new outbound client. On the ERP side it touches the Sales Order, the Customer masters, and a new integration role and user.
