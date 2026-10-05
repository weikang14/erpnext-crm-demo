# Design: shop-floor terminal (002-shopfloor-terminal)

## Why
ERPNext's Job Card form is built for planners, not for an operator wearing gloves. Real
factories put a simple tablet page at each station. This is that page, written in
**Django**, talking to ERPNext only through its REST API, so the owner can show Django
skills and an ERP integration in one piece. Research: `artifacts/market-research.md`.

## Architecture
```
tablet ──HTTP──> portal (Django 6.1, gunicorn, SQLite)  ──REST v2, token──> ERPNext backend:8000
                 ERP/portal/                                               (site "localhost")
```
- Service `portal` in `ERP/docker-compose.yml`, published on `127.0.0.1:8081`.
- Django keeps only operators, sessions and settings (SQLite in a volume). Every job,
  time log and defect lives in ERPNext; the portal never caches them.
- One ERPNext integration user (`shopfloor.terminal@ombakmetal.example`, least-privilege role
  "Shop Floor Terminal", see requirements AC17) with an API key/secret from site config. Each time log is booked to the
  operator's own ERPNext **Employee**, so ERPNext shows who did the work.

## Code layout
```
ERP/portal/
  Dockerfile, requirements.txt, manage.py
  portal/settings.py urls.py wsgi.py
  terminal/
    erpnext.py      ERPNext client: the only module that does HTTP (see api-contract.md)
    queue.py        pure logic: readiness, status, elapsed time
    models.py       Operator(user, employee, default_workstation)
    views.py forms.py urls.py
    management/commands/seed_operators.py
    templates/terminal/*.html  static/terminal/app.css app.js
    tests/          unit tests (fake client) + contract tests (live ERPNext)
```

## Behaviour
- **Queue** = the station's job cards with docstatus 0, oldest planned start first.
  Status: Running (open time log, not paused), Paused (`is_paused`), Ready (every earlier
  operation of the same work order submitted), Waiting (shows which operation it waits for).
  Timing label: Overdue / Today / Later. Order: running, paused, overdue, today, later.
- **Actions** call ERPNext's own Job Card methods (`start_timer`, `pause_job`,
  `resume_job`, `complete_job_card` with `auto_submit`), so ERPNext's sequence and overlap
  rules still apply. Times are sent as naive **Asia/Kuala_Lumpur** wall-clock strings
  (the site's time zone; sending UTC shifts logs by 8 h).
- **Complete** books the full remaining quantity (owner's decision: no partial completion;
  a paused card is resumed first, at the same instant) and
  then submits optional defect lines as Defect Logs. If a defect line is rejected the
  completion stands and the message says which line failed.
- **Errors:** ERPNext 4xx/417 → its message with HTML stripped; 401/5xx/connection error →
  "Can't reach the ERP" banner. Never a stack trace.

## Look
One stylesheet with CSS custom properties (tokens below), no framework, no inline styles.
System font stack; 18 px body; 64 px primary buttons; status colours: running #157F3D,
paused #B45309, waiting #6B7280, ready #1D4ED8, error #B91C1C on #F8FAFC background.
Single column on phones, cards 2-up from 900 px. A small script disables a button after
tap ("Working..."), runs the timer and refreshes the queue every 30 s when idle.
