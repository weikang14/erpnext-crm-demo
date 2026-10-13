# Sprint Contract: Django sales CRM

**ID:** 003
**Created:** 2026-10-05
**Status:** shipped 2026-10-14 (amended 2026-10-08: AC23-26)

## Goal
An internal B2B sales CRM for Ombak Metal Works, written in Django on PostgreSQL:
leads routed by region, opportunities through the factory's own stages, quotes from the
price list with manager approval for discounts above 10 %, and the four reports a sales
manager asks for. See `design.md` and `artifacts/market-research.md`.

## Acceptance Criteria

### Run
1. `docker compose up -d --build` in `CRM/` starts `db` (PostgreSQL 17) and `web`;
   http://localhost:8082 shows the sign-in page; the port is bound to 127.0.0.1.
   `python manage.py seed_demo` loads the demo team, products, accounts, leads, deals,
   quotes and activities, and running it twice changes nothing.
2. Signed-out users are redirected to sign-in (except `/enquiry/`); a wrong password
   shows an error; sign-out is a POST. Ten failed sign-ins for one username within
   15 minutes lock that username out for the rest of the window.

### Leads (table stakes 1, 2, 3)
3. A rep creates a lead (company, contact, email or phone, state, source, interest); the
   region comes from the state and the rep becomes the owner.
4. A web enquiry (`/enquiry/`, no sign-in) creates a lead with source Website, owned by the
   active rep of the region with the fewest open leads (tie: lowest id); with no active
   rep there it is unassigned and listed for the manager. A filled honeypot field or more
   than 5 enquiries per IP per hour creates nothing.
5. A lead page warns about possible duplicates: accounts with the same name (any case) and
   contacts or open leads with the same email.
6. Converting a lead creates (or reuses a chosen existing) account, a contact and an
   opportunity in Enquiry owned by the lead owner; the lead becomes Converted, links to the
   deal and can't be converted again. Disqualifying needs a reason.
7. The lead list filters by status, owner and region and searches company, contact and
   email; the manager can reassign a lead to another active rep.

### Accounts (4)
8. Reps can create accounts. The account page shows details, contacts, open and closed
   deals and activities; a contact or a new deal (repeat customers need no lead) can be
   added from it.

### Pipeline (5, 6, 7)
9. `/pipeline/` shows the four open stages as columns, each with deal count and total
   value. Each card shows title, account, value, expected close, owner (manager view), a
   next-activity indicator (overdue, today, none, future) and a stale flag (no activity or
   stage change for 14 days). Cards sort overdue, today, none, future.
10. A card moves to another open stage with its "Move to" control (works without
    JavaScript, by keyboard) or by drag and drop; each move is recorded in the deal's
    history (from, to, who, when). Moving to Quotation or Negotiation without a sent
    quote is refused with "Send a quote first".

### Activities (8)
11. On a lead, deal or account a user logs a done activity (call, meeting, visit, email,
    note) or schedules one with a due date, and ticks it done from the deal page or My day.
    Any activity updates the deal's "last activity" (clears the stale flag).
12. My day lists the user's overdue and today activities, own open deals with no next
    activity, stale deals and new leads; the manager also sees quotes waiting for approval
    and unassigned leads.

### Won / lost (9)
13. Marking a deal Won needs a sent quote; that quote becomes Accepted, the deal amount is
    its total and the deal is closed (read-only). Marking Lost needs a lost reason from the
    admin-editable list (plus an optional note); a sent quote becomes Declined.

### Quotes (10, 11)
14. A quote is created from a deal; lines pick an active product, the unit price is the
    list price and can't be edited; qty > 0 and discount 0 to 100 %. Line and quote totals
    are Decimal, rounded half-up to 2 dp, excluding SST.
15. Submitting a quote with any line above 10 % discount makes it Pending; at or below
    10 % (or a manager's own quote) makes it Approved. Only a manager approves or rejects
    (reject needs a note and returns it to Draft with the note shown); a rep's POST to
    approve gets 403.
16. Only Approved quotes can be sent or printed; Approved and Sent quotes can't be
    edited. Sending moves an earlier deal to Quotation and sets the deal amount to the
    quote total. "Revise" on a sent quote creates a new draft copy at today's list prices; the
    old one stays Sent until the revision is sent, then becomes Superseded. The print page shows company header, customer, lines, totals, validity
    and quote number, and prints cleanly on A4.

### Reports (12)
17. `/reports/` for a chosen quarter (default: current) shows: pipeline by open stage
    (count, value, weighted value); win rate per rep (won, lost, win % = won / (won + lost)
    by count, won value); forecast (won in quarter, weighted open pipeline closing in the
    quarter, forecast = won + weighted, best case = won + all open closing in the quarter);
    lost reasons (count, value, share). Reps see their own figures; the manager sees the
    team and can filter by region and rep.

### Lists, roles, look (13, 14)
18. The opportunity list filters by stage (open, won, lost, each stage), owner, region and
    close quarter, searches title and account, paginates 25 per page, and exports the
    filtered rows as CSV.
19. A rep never sees another rep's lead, deal, quote or activity: lists leave them out and
    their URLs answer 404. Manager-only pages and actions answer 403 to reps. `/admin/` is
    for staff; the manager can maintain products, lost reasons and reps there.
20. Every list has an empty state and a "no matches" state for filters; every form shows
    field errors next to the field; a database error shows a friendly 500 page without a
    stack trace.
21. Usable at 1440x900, 1024x768 and 390x844 with no horizontal page scroll; every
    control has a visible focus style and a 44 px minimum height; Lighthouse accessibility
    and best practices >= 90 on My day, pipeline and a quote page.

### Security and ops
22. DEBUG off, secret key and database password from env (documented demo defaults only),
    CSRF on every POST, CSP `default-src 'self'`, X-Frame-Options DENY, session cookie
    HttpOnly. State-changing views are POST only.

## Amendment 2026-10-08: editing and team view
Added by the user after alignment validation found that records could not be corrected
after creation (`.specship/artifacts/verdicts/alignment.json`). Same rules as above: access
through `access.py`, POST only with CSRF, field errors next to the field (AC20).

### Editing and reassignment
23. The deal owner or the manager edits an open deal's title, contact (one of the
    account's contacts), expected close and estimated value from the deal page. The value
    is locked once the deal has a sent quote (sending sets it, AC16). Won and lost deals
    stay read-only: their edit page and POST are refused.
24. The lead owner or the manager edits an open lead (New or Contacted) with the same
    fields and validation as creating one; changing the state changes the region, not the
    owner. Converted and disqualified leads are read-only. Any signed-in user edits an
    account (accounts are shared; the name stays unique, any case) and its contacts.
25. The manager reassigns an open deal to another active rep from the deal page (same
    control as lead reassign, AC7). The deal's open activities owned by the old owner move
    to the new owner; done activities keep their owner. A rep's POST gets 403; closed
    deals and inactive reps are refused.
26. On the manager's My day the open pipeline, "no next step" and stale panels cover the
    whole team, each deal showing its owner, and are labelled as the team's. The
    manager's overdue and today activities stay the manager's own. Reps' My day is
    unchanged (AC12).

## Failure Modes (what a lazy build would get wrong)
1. Discount approval bypassed by editing an approved quote, typing a lower unit price, or
   posting straight to send.
2. A rep reads another rep's deal by changing the id in the URL.
3. Money as float: 0.1 + 0.2 style totals, or rounding only the grand total.
4. Win rate counting open deals, or by value instead of count.
5. Forecast mixing quarters (uses created date instead of expected close / closed date).
6. Stage moved to Won with no quote, or Lost with no reason, by a crafted POST.
7. Round robin that always picks the first rep, or crashes when a region has no rep.
8. Enquiry form open to spam (no honeypot or rate limit) or leaking whether an email
   exists.
9. Lead converted twice, creating duplicate deals.
10. Board that only works with a mouse.
11. Seed that duplicates data on the second run.
12. Reports that run one query per deal (N+1) and crawl on real data.
13. Time zone bugs: "today" computed in UTC instead of Asia/Kuala_Lumpur.

## Scope
**In:** everything above, demo seed data, tests, README section.
**Out:** email/calendar sync, multi-currency (MYR only), taxes (ERPNext adds SST),
multi-level approval, reopening closed deals, file attachments, custom fields, REST API,
link to ERPNext (contract 004).

## Non-functional
- Python 3.13, Django 6.1, PostgreSQL 17, gunicorn gthread, whitenoise.
- Reports use aggregate queries (a constant number per report, not one per deal).
- Tests run in the container against PostgreSQL: `bash CRM/scripts/test.sh`.
