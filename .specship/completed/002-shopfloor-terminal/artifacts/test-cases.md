# Test cases: 002-shopfloor-terminal

Unit tests use a fake ERPNext client (no network). Contract tests hit the real ERPNext
`contract.localhost` site. Run all with `bash ERP/scripts/test-portal.sh`.

## Django unit tests (fake client)
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| AUTH-1 | 2 | signed out, GET / | 302 to /login/?next=/ |
| AUTH-2 | 2 | wrong password | 200, form error shown, not signed in |
| AUTH-3 | 2 | POST /logout/ | signed out; GET /logout/ -> 405 |
| ST-1 | 3 | operator default "Welding Bay" | picker lists fake workstations, Welding Bay selected |
| ST-2 | 3, FM9 | GET /?workstation=Laser Cutting, then GET / and an action | Laser Cutting kept |
| ST-3 | 3 | ?workstation=Nope (not in list) | ignored, previous station kept |
| Q-1 | 4 | cards seq 1 (siblings none), seq 2 (seq 1 docstatus 0) | chips Ready, "Waiting: waits for <op 1>" |
| Q-2 | 4 | card with open log, card with is_paused=1 | chips Running (first) and Paused |
| Q-3 | 4, FM5 | fake returns a card with status Completed | not shown |
| Q-4 | 11 | no cards | empty-state text + picker |
| ACT-1 | 5, FM1 | now = 2026-10-05 06:30 UTC; POST start | client.start(card, employee, "2026-10-05 14:30:00") |
| ACT-2 | 6 | POST pause / resume | client.pause(card, t) / client.resume(card, t) |
| ACT-3 | 7 | GET complete for for_quantity 10, completed 0 | form shows 10 |
| ACT-4 | 7, 8 | POST complete with 2 defect lines (1 blank) | client.complete(card, 10, t) then 2 defect calls; success message |
| ACT-5 | 8, FM8 | defect call raises ERPNextError("Only 3 more...") | completion message AND defect error both shown |
| ACT-6 | 9 | POST start on a card; client raises ERPNextError(sequence) | message shown, redirect to queue |
| ACT-7 | 15 | GET any action URL | 405 |
| ACT-8 | 15, FM10 | POST /job/..%2FUser%2FAdministrator/start/ or name "X-1" | 404, client never called |
| ERR-1 | 10 | client raises ERPNextUnavailable on queue | banner "Can't reach the ERP right now", retry link, no traceback |
| ERR-2 | 10, FM3 | ERPNextError message with `<strong>` and `<a>` | text shown without tags |
| ERR-3 | 10 | queue raises ERPNextError (e.g. running card deleted mid-request) | 502 page showing the message, retry link |
| REC-1 | 7 | Complete on a paused card | resume then complete at the same timestamp |
| REC-2 | FM2 | Start on a card with an open log; Resume on a card that isn't paused | refused with a message, ERPNext not called |
| REC-3 | 4 | Work In Progress card with no open log | shown as Ready, not Running |
| REC-4 | 4 | overdue / today / later boundaries and ordering (running, paused, overdue, today, later) | labels and order as specified |
| REC-5 | 15 | non-ASCII digits or trailing newline in a job card name | 404 / ValueError, ERPNext not called |
| REC-6 | 15 | any page | Content-Security-Policy default-src 'self'; /admin/ is 404 |
| SEC-1 | 15 | POST start without CSRF token (enforce_csrf_checks) | 403 |
| SEC-2 | FM4 | render every page | API secret string absent |
| UI-1 | 14, FM7 | scan templates | no `style=` attribute, no `onclick=` |
| UI-2 | 13, 14 | parse app.css | tokens defined; `.btn-primary` min-height >= 64px; buttons have :hover, :active, :focus-visible, :disabled rules |

## ERPNext client unit tests (mocked HTTP)
| ID | Expect |
|---|---|
| CL-1 | every request carries Host = site, `Authorization: token key:secret`, Accept json |
| CL-2 | 417 `{"errors":[{"message":"<strong>A</strong>"}]}` -> ERPNextError("A") |
| CL-3 | 401, 500, ConnectionError, timeout -> ERPNextUnavailable; 403 -> ERPNextError "Tell the supervisor" |
| CL-4 | start/pause/resume/complete/defect use the v2 paths and JSON bodies in api-contract.md |
| CL-5 | job card name is URL-quoted; invalid names raise ValueError before any request |

## Contract tests (live ERPNext, contract.localhost)
| ID | Expect |
|---|---|
| CT-1 | workstations list has the 4 stations, shape `{"data":[{"name"}]}` |
| CT-2 | queue rows contain every field the portal reads |
| CT-3 | start -> pause -> resume -> complete on a fresh job card: 2 time logs (start..pause, resume..complete) for the employee, docstatus 1, status Completed |
| CT-4 | defect insert -> docstatus 1; over cap -> ERPNextError mentioning "Only" |
| CT-5 | starting operation 2 before operation 1 -> ERPNextError with "before the operation" |
| CT-6 | wrong token -> ERPNextUnavailable (401) |
| CT-7 | the terminal token is refused Sales Invoice reads and Work Order creation ("Tell the supervisor") |

## ERPNext side (bench test suite)
| ID | AC | Expect |
|---|---|---|
| OP-1 | 17 | setup_masters creates 4 active operator Employees, one per workstation |
| OP-2 | 17 | integration user has only the "Shop Floor Terminal" role; api_key set from site config when configured |
| OP-3 | 17 | role allows Job Card read/write/submit, Work Order read/write/submit, Defect Log create/submit, Workstation/Employee/Defect Reason read; denies Sales Invoice, Account, BOM, Stock Entry, Work Order create/cancel/delete, editing other users |

## Browser / design (validators)
1. Sign in as an operator -> pick a station -> Start a Ready card -> timer ticks -> Pause ->
   Resume -> Complete with one defect line -> card gone, message shown; check ERPNext Desk
   shows the time logs and the Defect Log.
2. Waiting card has no Start; empty station shows empty state.
3. Stop ERPNext backend -> banner; start it again -> retry works.
4. 1024x768, 768x1024, 390x844 screenshots: no horizontal scroll, button sizes.
5. Lighthouse mobile >= 90 (performance, accessibility, best practices).
