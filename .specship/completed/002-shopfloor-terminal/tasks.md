# Plan: 002-shopfloor-terminal

Each task: test from `artifacts/test-cases.md` -> RED -> implement -> GREEN -> commit.
Portal tests: `bash ERP/scripts/test-portal.sh`. ERPNext tests: `bash ERP/scripts/test.sh`.

## Milestone 1: Scaffold + verify it runs
### Task 1.1: Django 6.1 project `ERP/portal` (project `portal`, app `terminal`), Dockerfile (python:3.13-slim, gunicorn, whitenoise), `portal` service on 127.0.0.1:8081, SQLite volume, settings from env (TZ Asia/Kuala_Lumpur, DEBUG off).
### Task 1.2: `scripts/test-portal.sh`; first test: GET /login/ is 200. Verify http://localhost:8081/login/ in a browser.

## Milestone 2: ERPNext side
### Task 2.1: masters: 4 operator Employees (one per workstation) + integration user with API key/secret from site config (`shopfloor_api_key`, `shopfloor_api_secret`). Tests OP-1, OP-2.
### Task 2.2: compose `create-site` sets those site-config keys from env (demo defaults); test-portal.sh prepares `contract.localhost` the same way.

## Milestone 3: ERPNext client
### Task 3.1: `terminal/erpnext.py` per api-contract.md. Tests CL-1..CL-5.
### Task 3.2: contract tests CT-1..CT-6 (fresh work order created by a bench command before the run).

## Milestone 4: Sign-in, station, queue
### Task 4.1: Operator model + admin + `seed_operators` command (maps Django users to ERPNext Employees). Tests AUTH-1..3.
### Task 4.2: design system: base template, app.css tokens, components. Tests UI-1, UI-2.
### Task 4.3: `queue.py` readiness/status + queue view + station picker + empty state. Tests ST-1..3, Q-1..4.

## Milestone 5: Actions and error states
### Task 5.1: start / pause / resume views (POST, name validation, local time). Tests ACT-1, ACT-2, ACT-6..8, SEC-1.
### Task 5.2: complete form + defect lines. Tests ACT-3..5.
### Task 5.3: error handling + banner + loading JS + timer + auto refresh. Tests ERR-1, ERR-2, SEC-2.

## Milestone 6: Polish and proof
### Task 6.1: responsive + accessibility pass at the three sizes; Lighthouse >= 90.
### Task 6.2 (SHIP phase, not counted in build tasks): README section for the terminal.
