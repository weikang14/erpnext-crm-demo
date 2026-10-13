# Plan: 003-django-crm

Each task: test from `artifacts/test-cases.md` -> RED -> implement -> GREEN -> commit.
Tests: `bash CRM/scripts/test.sh` (Django TestCase on PostgreSQL in the `web` container).

## Milestone 1: Scaffold + verify it runs
### Task 1.1: Django 6.1 project in `CRM/` (project `crm`, app `sales`), Dockerfile (python:3.13-slim, gunicorn gthread, whitenoise, psycopg), compose with `db` (postgres:17-alpine, healthcheck) and `web` on 127.0.0.1:8082; settings from env (TZ Asia/Kuala_Lumpur, DEBUG off, CSP, cookies).
### Task 1.2: `scripts/test.sh`; login/logout views; tests RUN-1, AUTH-1..3, SEC-4. Verify http://localhost:8082/login/ in a browser.

## Milestone 2: Data model, rules, seed
### Task 2.1: models + migration + admin (products, lost reasons, reps). `regions.py`. Tests REG-1, ADM-1.
### Task 2.2: `rules.py`: line/quote totals, approval need, stage gates. Tests Q-1, Q-2, QA-1..3 (pure), MOVE-2/3, WON-1 (pure).
### Task 2.3: `seed_demo` (team, products = ERPNext FG codes, accounts incl. the 5 ERPNext customers, leads, deals over 5 quarters, quotes, activities; deterministic, idempotent). Test RUN-2.

## Milestone 3: Shell, access, leads, accounts
### Task 3.1: design system (base template, nav, app.css tokens, messages, empty states, 500 page) + `access.py`. Tests UI-1..3, SEC-1..3, SEC-5.
### Task 3.2: leads: list/filter/search, create, detail with duplicates, assign, disqualify, convert. Tests LEAD-1/2, DUP-1/2, CONV-1..3, DISQ-1, LL-1/2.
### Task 3.3: enquiry form + rate limiter (also on login). Tests ENQ-1..6, AUTH-4.
### Task 3.4: accounts list/detail + contacts + activities (log, schedule, done). Tests ACC-1, ACT-1..3.

## Milestone 4: Opportunities and pipeline
### Task 4.1: opportunity list (filters, pagination, CSV) + detail (history, quotes, activities). Tests LIST-1..3.
### Task 4.2: pipeline board + move (form + drag and drop JS). Tests PIPE-1..4, MOVE-1..4.
### Task 4.3: won / lost. Tests WON-1/2, LOST-1/2, CLOSED-1.

## Milestone 5: Quotes and approvals
### Task 5.1: quote create + line editor + submit. Tests Q-3, Q-4, QA-1/2 (views).
### Task 5.2: approvals page + approve/reject. Tests QA-3..6, SEC-2.
### Task 5.3: send, revise, print (A4 print CSS). Tests QS-1..4, QP-1.

## Milestone 6: My day and reports
### Task 6.1: My day. Tests DAY-1..3.
### Task 6.2: `reports.py` + reports page with SVG bars. Tests REP-1..7.

## Milestone 7: Polish and proof
### Task 7.1: responsive + accessibility pass at 3 sizes; Lighthouse >= 90 (probe script).
### Task 7.2 (SHIP phase, not counted): README section + screenshots.

## Milestone 8: Editing and team view (amendment 2026-10-08, AC23-26)
### Task 8.1: deal edit (reuse `DealForm`; value locked after a sent quote; closed deals refused) + manager deal reassign (reuse `AssignForm`; open activities move). Tests EDIT-1..5, RA-1..3.
### Task 8.2: lead edit (reuse `LeadForm`, open leads only), account edit (reuse `AccountForm`), contact edit. Tests EDIT-6..9.
### Task 8.3: manager's My day shows the team's open pipeline, no-next-step and stale deals with owners. Tests DAY-4, DAY-5.
