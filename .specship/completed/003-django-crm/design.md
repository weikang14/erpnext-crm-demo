# Design: Django sales CRM (003-django-crm)

## Why
Ombak Metal Works sells cable trays, machine guards, racks and frames to contractors and
factories in Malaysia and Singapore. Sales today live in WhatsApp and Excel. This CRM is
the sales team's own system, written in **Django**: leads come in, are routed to the
rep for that region, become opportunities, get a quote from the price list (big discounts
need the sales manager), and end as won or lost with a reason. Managers get pipeline,
win-rate, forecast and loss-reason reports. Contract 004 will push won deals into ERPNext
as sales orders, so product codes match ERPNext items from day one.
Research: `artifacts/market-research.md`.

## Architecture
```
browser ──HTTP──> web (Django 6.1, gunicorn gthread, whitenoise) ──> db (PostgreSQL 17)
                  CRM/                                               volume crm-db
```
- Own compose file `CRM/docker-compose.yml` (separate system from the ERP, as the owner
  asked); `web` on `127.0.0.1:8082`. No link to ERPNext yet (that is 004).
- PostgreSQL rather than SQLite: reports aggregate across thousands of rows, and the
  stack matches what an employer runs.
- Server-rendered templates, one stylesheet, one small script. The UI calls
  opportunities "deals" (shorter, and what reps say); the code says Opportunity. No SPA, no CSS framework.
- Django admin at `/admin/` for master data (products, lost reasons, users, rep regions),
  staff only.

## Code layout
```
CRM/
  Dockerfile  docker-compose.yml  requirements.txt  manage.py  .dockerignore
  crm/            settings.py urls.py wsgi.py
  sales/
    models.py     Account Contact Lead Opportunity StageChange Activity Product
                  Quote QuoteLine LostReason SalesRep
    regions.py    state -> region table, round-robin owner pick
    rules.py      stage gates, quote approval, totals (pure functions, no HTTP)
    reports.py    pipeline, win rate, forecast, loss reasons (querysets in, rows out)
    access.py     who may see / change what (one place)
    ratelimit.py  cache-based limiter for the enquiry form and login
    forms.py  admin.py  urls.py
    views/        home leads accounts opportunities quotes reports enquiry
    management/commands/seed_demo.py
    templates/sales/  static/sales/app.css app.js
    tests/
  scripts/test.sh
```

## Data model (main fields)
- **SalesRep**(user 1:1, region, active). Managers are users in group "Sales Manager".
- **Account**(name, registration no, industry, address, city, state, postcode, phone,
  owner). `region` and `country` come from `state`.
- **Contact**(account, name, job title, email, phone).
- **Lead**(company, contact name, email, phone, state, source, interest, notes, status
  new/contacted/converted/disqualified, disqualify reason, owner, opportunity).
- **Opportunity**(title, account, contact, owner, stage, amount, expected close,
  lost reason, lost note, closed at, last activity at, source lead).
- **StageChange**(opportunity, from, to, by, at): history shown on the deal page.
- **Activity**(kind call/meeting/visit/email/task/note, subject, notes, due date, done,
  done at, owner, and one of lead / opportunity / account).
- **Product**(item code = ERPNext item code, name, uom, list price, active).
- **Quote**(opportunity, status draft/pending/approved/sent/accepted/declined/superseded,
  valid until, created by, approved by, approved at, decision note, sent at). Number
  `QT-<year>-<id:05d>`, so it is unique without a counter table.
- **QuoteLine**(quote, product, qty, unit price copied from the list price, discount %).
- **LostReason**(name, active), editable in admin.

## Rules
- **Regions:** North (Perlis, Kedah, Penang, Perak, Kelantan, Terengganu), Central
  (Selangor, Kuala Lumpur, Putrajaya, Negeri Sembilan, Pahang, Sabah, Sarawak, Labuan),
  South (Johor, Melaka), Singapore. East coast and East Malaysia go to the nearest team;
  the table is one dict in `regions.py`.
- **Lead owner:** a rep who types a lead owns it. Web enquiries and manager-entered leads
  without an owner go to the active rep in the lead's region with the fewest open leads
  (tie: lowest id). No active rep in the region: unassigned, shown to the manager.
- **Stages and probability:** Enquiry 10, Technical review / sampling 25, Quotation 50,
  Negotiation 75, Won 100, Lost 0. Open stages move freely, except Quotation and
  Negotiation need a sent quote. Sending a quote moves an earlier deal to Quotation and
  sets the deal amount to the quote total.
- **Won** needs a sent quote, which becomes accepted. **Lost** needs a lost reason; a sent
  quote becomes declined. Closed deals are read-only.
- **Quotes:** price comes from the product list and is not editable; the only lever is a
  per-line discount 0 to 100 %. Any line above **10 %** sends the quote to the manager
  (pending). A manager's own quote is approved on submit. Manager approves, or rejects
  with a note (back to draft). Only approved quotes can be printed or sent. Approved and
  sent quotes are locked; "Revise" copies a sent quote into a new draft at today's list
  prices; the old quote stays Sent (the customer still holds it) until the revision is sent,
  then it becomes Superseded. One quote in progress (draft, pending or approved) per deal.
- **Money:** Decimal, rounded half-up to 2 dp per line; totals exclude SST (ERPNext adds
  tax on the sales order).
- **Visibility:** reps see their own leads, opportunities, quotes and activities, and all
  accounts. Managers see everything and can reassign. Another rep's record answers 404.
- **Stale deal:** open deal with no activity or stage change for 14 days.
- **Next-activity indicator:** overdue (red), today (green), none (amber warning), future
  (grey); the board sorts cards in that order.

## Pages
| URL | Who | What |
|---|---|---|
| `/` | all | My day: overdue/today activities, deals without a next activity, stale deals, new leads; manager adds approvals and unassigned leads |
| `/pipeline/` | all | Board: 4 open stage columns with count and value, "Move to" per card, drag and drop |
| `/leads/`, `/leads/new/`, `/leads/<id>/` (+ convert, disqualify, assign) | all | Lead list and detail |
| `/accounts/`, `/accounts/<id>/` | all | Accounts with contacts, deals, activities |
| `/opportunities/` (+ `?format=csv`), `/opportunities/<id>/` (+ move, won, lost) | all | Deal list and detail with quotes, activities, history |
| `/quotes/<id>/` (+ lines, submit, approve, reject, send, revise, print) | all | Quote editor and print view |
| `/approvals/` | manager | Quotes waiting for approval |
| `/reports/` | all | Pipeline by stage, win rate by rep, quarter forecast, loss reasons |
| `/enquiry/` | public | Web enquiry form, creates an auto-assigned lead |
| `/login/`, `/logout/`, `/admin/` | | |

## Look
Same family as the shop-floor terminal, denser because it is a desk app. Tokens on
`:root`: background #F8FAFC, surface #FFFFFF, text #0F172A, muted #475569, border
#CBD5E1, accent #1D4ED8, green #157F3D, amber #B45309, red #B91C1C, grey #6B7280,
focus #C2410C. System font stack, 16 px body, 14 px tables, 8 px spacing grid, 44 px
minimum control height. Top bar with section links and the manager's approval count.
Board columns side by side from 1024 px, stacked below. Charts are server-rendered SVG
bars (CSP allows them, no chart library). No inline styles or scripts.
