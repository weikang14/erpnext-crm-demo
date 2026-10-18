# Changelog

## 2026-10-18: Part 3, CRM → ERPNext sales orders (contract 004)

- **The link:** marking a deal Won in the CRM creates a submitted ERPNext sales order in the same request, through ERPNext's REST API.
  - The rep enters a requested delivery date at Won: default today + 14, at most 365 days ahead.
  - Missing customers are created, with a billing address when the account has one.
  - Lines go at the quote's list price, with one header discount, so the order's net total equals the quote to the sen.
  - Malaysian customers get the new "Malaysia SST - OMW" template (10 %); Singapore customers get no tax (export).
  - Won never depends on ERPNext. A failed send shows the reason and a Send again form on the deal, and appears on My day.
  - The quote number in the unique `crm_reference` field plus lookup-first sending means a retry can't create a second order.
- **ERP side (`setup_masters`, idempotent):** the role *CRM Integration* and its API user, the `crm_reference` custom field, an SST account and template. The 19 demo orders are unchanged.
- **Running it:** an optional compose override (`CRM/docker-compose.erp.yml`) puts the CRM on a network it shares only with the ERPNext backend.
- **Fixed during deploy and validation:**
  - **First real send refused (403):** the integration role couldn't read the customer's address, which belonged to Administrator. It now reads addresses.
  - **Order status stuck on "Draft":** inserting an order already submitted skips ERPNext's status update. Orders are now created as drafts, then submitted.
  - **Network exposure:** the CRM container joined the whole ERP network, with Redis and MariaDB in reach. It now has a backend-only link network.
  - **Too much access:** the integration user could change or submit sales orders it didn't create. Its Sales Order rule is now `if_owner`.
  - **500 errors after Won:** order names repeated across ERPNext sites collided in the CRM, and a database error while claiming the send was unhandled. Both now end as a visible failed send, and Won is kept.
  - **No upper limit on the delivery date:** now 365 days.
  - The refusal message says the deal stays won, and the panel shows the delivery date.
- **Testing:**
  - 331 CRM tests, 17 of them live contract tests on a separate `contract.localhost` site;
  - 50 ERPNext tests (was 32) and 63 terminal tests;
  - the UI probe covers the won deal's ERP panel;
  - Lighthouse 100/100/100 on the panels.
- **Validation:** independent code, security, integration, browser, design and alignment passes all PASS, with a skeptic re-check of the cycle-1 fixes and a completeness critic. Recovery took 2 of 3 rounds.
- **Known issues:** see the README's part 3 list. The main one: ERPNext's `/printview` lets the integration key read any sales order (read-only, medium, accepted).

## 2026-10-14: Part 2, sales CRM (contract 003)

- **The app:** a Django 6.1 + PostgreSQL 17 sales CRM in `CRM/`, at http://localhost:8082.
  - Leads routed by region (round robin), plus a public enquiry form with a honeypot and a rate limit.
  - Duplicate warnings, and lead conversion.
  - Accounts and contacts, activities, and a pipeline board (keyboard "Move to" and drag and drop) with stage gates.
  - Won/lost with reasons.
  - Quotes from the ERPNext price list, with manager approval above 10 % discount, send, revise and an A4 print page.
  - My day, quarterly reports (pipeline, win rate, forecast, lost reasons) and a CSV export.
- **Added after the first validation round (contract amendment AC23-26):**
  - editing for deals, leads, accounts and contacts (a deal's value locks once a quote is sent);
  - the manager reassigns deals;
  - the manager's My day shows the whole team.
- **Fixed during validation:**
  - **Discount approval:** an unapproved discount could reach an Approved quote, first through a race between adding a line and Submit, then through a stale Approve or Finish page. The quote is now row-locked and carries a revision number.
  - **Admin rights:** a sales manager could make themselves superuser in `/admin/`. The user admin is now guarded.
  - **Sign-in lockout:**
    - look-alike Unicode usernames got their own counters;
    - `/admin/login/` skipped the lockout;
    - parallel attempts could get more than 10 password checks.
    The lockout is now one atomic counter shared by every sign-in path.
  - **Layout:** the approvals and draft-quote pages scrolled sideways on phones.
  - **Form errors:** four forms showed errors at the top of the page and lost what was typed. Errors now sit next to the field, and focus moves to it.
- **Testing:** 155 Django tests; the UI probe now covers 3 sizes, the approvals and draft-quote pages, and focus after an error; Lighthouse 100/100/100.
- **Validation:** independent code, security, integration, browser, design and alignment passes all PASS, with a skeptic re-check of the security fixes and a completeness critic covering 39/39 criteria.
  - Recovery took 4 rounds. The 4th was authorised by the user beyond the 3-round budget.
  - The user also approved a targeted re-run after round 3: security and alignment last ran on 4d7b80d, and the critic confirmed the later changes don't touch what they covered.
- **Known issues (low severity):**
  - A sign-in that succeeds at the same moment as a failed attempt for that username can raise a 500 (`ratelimit.hit`/`clear` race). It fails safe: nobody is signed in.
  - While locked, `/admin/login/` shows Django's generic error instead of "Too many attempts".
  - There is no unlock button (see the README for the shell command).
  - The lockout key lower-cases the name, so two accounts that differ only in case share one counter.
  - An account name using a look-alike letter of an existing name fails with no message (the duplicate check uses `iexact`, the database rule `Lower`).
  - A manager can reset another non-superuser's password in `/admin/`.
  - Text inputs with an error keep a grey border.
  - The activity date says "(optional)" although a planned activity needs one.
  - Deal pages are 331 px wide at 320 px.
  - The Dockerfile still runs a now-unneeded `createcachetable`.

## 2026-10-05: Part 1, Django shop-floor terminal (contract 002)

- Django 6.1 terminal (`ERP/portal`, http://localhost:8081): operators sign in, pick a workstation, and Start / Pause / Resume / Complete job cards and log defects; everything is written to ERPNext through REST v2.
- Queue with Running / Paused / Ready / Waiting status and Overdue / Today / Later labels; paused cards complete in one step; server-side guards against double starts.
- ERPNext side: 4 operator Employees and a least-privilege API role ("Shop Floor Terminal") with the key/secret from site config.
- 63 Django tests (unit + live contract tests against a separate ERPNext site) and 32 ERPNext tests. Lighthouse mobile 100/100/100.
- Independent code, security, alignment, integration, browser and design validation: all PASS after two recovery rounds (a paused card could not be completed; a scratch file with a test-site admin token had reached the image and was removed and the key rotated).
- Stack: nginx and the realtime service now follow backend restarts.

## 2026-10-04: Part 1, factory ERP (contract 001)

- ERPNext v16 Docker stack (adapted from frappe_docker `pwd.yml`; realtime works on localhost, port bound to 127.0.0.1).
- `ombak_mfg` app: Defect Log and Defect Reason doctypes; Work Order On-Time Rate, Workstation Load, Operation Time Variance and Defect Pareto reports; daily overdue-work-order alert; Ombak Factory workspace with 3 number cards.
- Idempotent master-data setup and a one-month demo-data generator (sales order → production plan/MRP → purchasing with inspection → work orders and job cards → delivery trip → invoice), plus a demo smoke check.
- 29 integration tests. Independent code, security, alignment and browser validation: all PASS.
