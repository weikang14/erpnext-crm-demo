# Sprint Contract: Django shop-floor terminal

**ID:** 002
**Created:** 2026-10-05
**Status:** validated (shipped locally 2026-10-05)

## Goal
A Django tablet page for factory operators that lists a workstation's job cards and lets
an operator start, pause, resume and complete them and log defects, writing everything to
ERPNext through its REST API. See `design.md`, `artifacts/market-research.md`,
`artifacts/api-contract.md`.

## Acceptance Criteria

1. `docker compose up -d --build` in `ERP/` also starts the portal; http://localhost:8081
   shows the sign-in page; the port is bound to 127.0.0.1.
2. Signed-out users are redirected to sign-in; a wrong password shows an error; a signed-in
   operator can sign out (POST).
3. The station picker lists ERPNext workstations; it defaults to the operator's station and
   the choice is kept for the rest of the session.
4. The queue shows all of the station's open job cards (docstatus 0), each with job card,
   item name, quantity, planned window, a status chip (Running, Paused, Ready or Waiting,
   "waits for <operation>") and a timing label: Overdue (planned end passed), Today (planned
   to start by end of today) or Later. Order: running, paused, then overdue, today, later,
   planned order within each group. *(Amended 2026-10-05, owner's decision: "today's job
   cards" means all open cards with Overdue/Today/Later labels, so overdue work stays visible.)*
5. Start on a Ready card creates an open ERPNext time log for the operator's Employee with
   `from_time` = now in Asia/Kuala_Lumpur (within 2 minutes); the card shows Running with a
   ticking timer.
6. Pause closes the open time log and shows Paused; Resume opens a new time log and shows
   Running again.
7. Complete books the full remaining quantity (owner's decision: no partial completion);
   confirming submits the ERPNext job card (status Completed, last log carries the completed
   qty), the card leaves the queue and a success message is shown. A paused card is resumed
   and completed at the same instant (ERPNext won't submit a card that is On Hold).
8. Defect lines entered on Complete (reason + qty, up to 3) become submitted Defect Logs in
   ERPNext. If ERPNext rejects a line (e.g. qty too high) its message is shown and the
   completion still stands.
9. Waiting cards have no Start button; a forced start (POST) shows ERPNext's sequence message
   and changes nothing.
10. ERPNext 4xx/417 errors are shown as their message without HTML tags (403 as a "tell the
    supervisor" permission message); 401, 5xx or no connection show a "Can't reach the ERP
    right now" page with a retry link; an ERPNext refusal while loading the queue shows its
    message on the same page (HTTP 502); no stack traces reach the page.
11. A station with no open job cards shows an empty state with the station picker.
12. After tapping an action the button is disabled and reads "Working..." so a double tap
    cannot send twice.
13. At 1024x768, 768x1024 and 390x844 there is no horizontal scroll; primary buttons are at
    least 64 px tall; touch targets are at least 48 px with at least 8 px between them.
14. All styling comes from one stylesheet with tokens; no inline styles; buttons have
    visible hover, active, focus and disabled states.
15. Every action is POST with CSRF; every view requires sign-in; job card names must match
    `^PO-JOB\d+$` before any ERPNext call; the API key/secret and Django secret come from
    the environment.
16. Lighthouse (mobile) on the queue page scores >= 90 for performance, accessibility and
    best practices.
17. ERPNext side: master setup creates 4 operator Employees and the integration user with
    the API key/secret from site config and only the least-privilege role "Shop Floor
    Terminal" (Job Card read/write/submit, Work Order read/write/submit because completing a
    job card updates its submitted work order, Workstation/Employee read, Defect Log
    create/submit, Defect Reason read); `bash ERP/scripts/test.sh` still passes. *(Amended
    2026-10-05, owner's decision: replaced Manufacturing User.)*
18. `bash ERP/scripts/test-portal.sh` runs the Django unit tests and the live contract
    tests against ERPNext and exits 0.

## Failure Modes
1. Times sent in UTC, so ERPNext logs are 8 h off.
2. A double tap starts the same job twice or creates overlapping logs.
3. ERPNext's HTML (links, `<strong>`) is rendered or shown as raw tags.
4. The API secret appears in a template, log line or error page.
5. Completed or cancelled job cards still appear in the queue.
6. Mixing v1 and v2 endpoints so errors are parsed from the wrong shape.
7. Inline styles, hover-only controls or buttons smaller than the contract sizes.
8. A rejected defect line rolls back or hides a completion that ERPNext already recorded.
9. The station resets to the default after every action.
10. A crafted job card name (e.g. `../User/Administrator`) reaches the ERPNext URL.

## Scope
**IN:** the portal service, operator mapping, queue, start/pause/resume/complete, defect
lines, error/empty/loading states, responsive layout, tests, ERPNext-side master data for
operators and the integration user.
**OUT:** partial completion, barcode scanning, offline mode, PIN quick-switch, quality
check steps, material transfer, any manager screens (ERPNext Desk covers them), the CRM.

## Design Spec
- Design system: one CSS file with custom properties; no framework.
- Palette: background #F8FAFC, surface #FFFFFF, text #0F172A, muted #475569, border
  #CBD5E1, ready #1D4ED8, running #157F3D, paused #B45309, waiting #6B7280, error #B91C1C.
- Type: system UI stack; 18 / 22 / 28 / 40 px; tabular numerals for the timer.
- Layout: header (station picker, operator, sign out) + queue; running jobs first; one
  column under 900 px, two columns above.
- Components: card, status chip, primary/secondary/danger buttons (64 px), select, number
  input with numeric keypad, message banner.
- Icons: none (text labels, readable with gloves on).
- Dark mode: no (bright factory lighting).

## Non-Functional Requirements
- Performance: queue page < 1 s server time with 20 job cards; Lighthouse >= 90.
- Security: AC15; portal bound to 127.0.0.1; DEBUG off by default.
- Accessibility: labels on every control, focus visible, messages in an aria-live region.

## Risks & Unknowns
- ERPNext permissions for the integration user's narrow role: confirmed by the live
  contract tests (CT-3 full cycle, CT-7 refusals).
- Lighthouse needs Chrome inside or next to the stack.

## Execution Config
```yaml
autonomy: guided
```

## Pre-Generated Test Cases
See `artifacts/test-cases.md`.
