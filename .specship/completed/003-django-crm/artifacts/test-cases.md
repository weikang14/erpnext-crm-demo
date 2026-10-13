# Test cases: 003-django-crm

Django TestCase against PostgreSQL in the `web` container: `bash CRM/scripts/test.sh`.
Fixtures: a manager, reps North (Aisyah), Central (Kumar, Jason), South (Siti), Singapore
(Wei Ling), 5 products, 3 lost reasons. "rep" = Siti unless stated.

## Run and auth
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| RUN-1 | 1 | GET /login/ | 200, sign-in form |
| RUN-2 | 1, FM11 | seed_demo twice | same row counts after the second run |
| AUTH-1 | 2 | signed out, GET /pipeline/ | 302 to /login/?next=/pipeline/ |
| AUTH-2 | 2 | wrong password | 200, error, not signed in |
| AUTH-3 | 2 | POST /logout/; GET /logout/ | signed out; 405 |
| AUTH-4 | 2 | 10 wrong passwords, then the right one | 11th attempt refused with "Too many attempts" |

## Regions and leads
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| REG-1 | 3 | state Penang / Johor / Pahang / Singapore | North / South / Central / Singapore |
| LEAD-1 | 3 | rep posts a new lead, state Johor | owner = rep, region South, status New |
| LEAD-2 | 3 | lead with neither email nor phone | form error |
| ENQ-1 | 4, FM7 | Central: Kumar 2 open leads, Jason 1; web enquiry state Selangor | owner Jason |
| ENQ-2 | 4, FM7 | Kumar 1, Jason 1 | owner = lower id |
| ENQ-3 | 4, FM7 | all Singapore reps inactive; enquiry from Singapore | owner None, listed for manager on My day |
| ENQ-4 | 4, FM8 | honeypot filled | no lead, thank-you page shown anyway |
| ENQ-5 | 4, FM8 | 6 posts from one IP in an hour | 6th creates nothing, 429 |
| ENQ-6 | 4 | GET /enquiry/ signed out | 200 |
| DUP-1 | 5 | account "Mutiara Automation Sdn Bhd"; lead company "mutiara automation sdn bhd" | duplicate warning names the account |
| DUP-2 | 5 | open lead and contact with the same email | both listed |
| CONV-1 | 6 | convert with "new account" | account, contact, deal (Enquiry, owner = lead owner); lead Converted + linked |
| CONV-2 | 6 | convert choosing an existing account | no new account |
| CONV-3 | 6, FM9 | convert the same lead again (POST) | refused, still one deal |
| DISQ-1 | 6 | disqualify without reason / with reason | error / status Disqualified |
| LL-1 | 7 | filter status=new, region=South, q=email part | only matching rows |
| LL-2 | 7, 19 | rep posts reassign | 403; manager reassigns, owner changes |

## Accounts and activities
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| ACC-1 | 8 | account page | contacts, deals, activities shown; add contact works |
| ACT-1 | 11 | log a done call on a deal | listed; deal last_activity_at = now |
| ACT-2 | 11 | schedule task due tomorrow; tick done | done, done_at set |
| ACT-3 | 11 | rep ticks another rep's activity | 404 |
| DAY-1 | 12, FM13 | activities due yesterday / today (KL) / tomorrow; now = 23:30 KL | My day: overdue 1, today 1 |
| DAY-2 | 12 | open deal with no future activity; deal idle 15 days | both listed |
| DAY-3 | 12 | manager with 1 pending quote, 1 unassigned lead | both listed; rep sees neither |

## Pipeline
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| PIPE-1 | 9 | 3 Enquiry deals (100, 200, 300.50) | column count 3, value 600.50 |
| PIPE-2 | 9 | deals with overdue / today / none / future next activity | that order; indicator labels |
| PIPE-3 | 9 | deal last touched 15 days ago | stale flag |
| PIPE-4 | 9 | closed deals | not on the board |
| MOVE-1 | 10 | move Enquiry -> Technical | stage changed; StageChange(from, to, by) |
| MOVE-2 | 10, FM6 | move to Quotation with no sent quote | refused "Send a quote first", stage unchanged |
| MOVE-3 | 10 | move to Won/Lost through the move URL | refused (must use won/lost) |
| MOVE-4 | 10 | board HTML | each card has a labelled "Move to" select and button |

## Won / lost
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| WON-1 | 13, FM6 | POST won, no sent quote | refused, still open |
| WON-2 | 13 | sent quote 1,000.00; POST won | deal Won, amount 1000.00, closed_at set; quote Accepted |
| LOST-1 | 13, FM6 | POST lost without reason | form error, still open |
| LOST-2 | 13 | lost with reason + sent quote | Lost, reason stored, quote Declined |
| CLOSED-1 | 13 | move / add quote on a closed deal | refused |

## Quotes
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| Q-1 | 14, FM3 | line FG-CT-300 (85.00) x 3, 7.5 % | line total 235.88 (255 x 0.925 = 235.875 half-up) |
| Q-2 | 14, FM3 | lines 0.10 x 1 and 0.20 x 1 | total 0.30 exactly (Decimal) |
| Q-3 | 14, FM1 | POST unit_price=1 with a line | ignored, price = list price |
| Q-4 | 14 | qty 0, discount 101, inactive product | field errors |
| QA-1 | 15 | max discount 10 % | submit -> Approved |
| QA-2 | 15 | a line at 10.01 % | submit -> Pending |
| QA-3 | 15 | manager's own quote at 25 % | submit -> Approved, approved_by = manager |
| QA-4 | 15, FM1 | rep POSTs approve | 403, still Pending |
| QA-5 | 15 | manager rejects without / with note | error / Draft + note shown |
| QA-6 | 15 | manager approves | Approved, approved_by, approved_at |
| QS-1 | 16, FM1 | POST send on Draft or Pending | refused |
| QS-2 | 16, FM1 | POST a line edit on Approved | refused |
| QS-3 | 16 | send Approved quote on an Enquiry deal | Sent, deal Quotation, amount = total |
| QS-4 | 16 | revise Sent quote, then send the revision | new Draft with same products and discounts; old stays Sent until the revision is sent, then Superseded |
| QP-1 | 16 | print Draft | 404; print Approved shows number, customer, lines, total, validity |

## Reports
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| REP-1 | 17 | open deals per stage | count, value, weighted (value x prob) |
| REP-2 | 17, FM4 | rep: 3 won, 1 lost, 2 open in quarter | win rate 75 % |
| REP-3 | 17, FM5 | won this quarter 1,000; Negotiation 2,000 closing this quarter; Enquiry 5,000 closing next quarter | won 1000, weighted 1500, forecast 2500, best case 3000 |
| REP-4 | 17 | 2 lost "Price too high" (1000, 500), 1 "Lead time" (500) | counts 2/1, value, share 67 % / 33 % |
| REP-5 | 17, 19 | rep opens reports | only own figures; manager sees all, filter by region |
| REP-6 | 17, FM12 | 30 deals | reports page runs <= 15 queries |
| REP-7 | 17 | ?quarter=garbage | current quarter, no 500 |

## Lists, access, look
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| LIST-1 | 18 | 30 deals | page 1 has 25, page 2 has 5 |
| LIST-2 | 18 | filter stage=won, q=title part | only matching |
| LIST-3 | 18 | ?format=csv | text/csv, header row, filtered rows, no other rep's rows |
| SEC-1 | 19, FM2 | rep GETs another rep's lead, deal, quote | 404 each |
| SEC-2 | 19 | rep GETs /approvals/ | 403 |
| SEC-3 | 22 | POST without CSRF token | 403 |
| SEC-4 | 22 | any page | CSP default-src 'self'; X-Frame-Options DENY |
| SEC-5 | 22 | GET on any state-changing URL | 405 |
| UI-1 | 20 | empty lead list; filter with no match | "No leads yet" / "No leads match" |
| UI-2 | 20 | forced DB error in a view | 500 page, no traceback text |
| UI-3 | 21 | templates | no `style=` attributes, no inline `<script>` |
| ADM-1 | 19 | manager GETs /admin/sales/product/ | 200; rep -> redirect to admin login |

## Amendment 2026-10-08: editing and team view
| ID | AC/FM | Given | Expect |
|---|---|---|---|
| EDIT-1 | 23 | owner posts a new expected close and value on an open deal with no sent quote | saved; deal page and forecast use the new values |
| EDIT-2 | 23 | deal with a sent quote; owner posts a different value | value unchanged (field locked or ignored); other fields saved |
| EDIT-3 | 23, 19 | another rep GETs / POSTs the deal's edit URL | 404 |
| EDIT-4 | 23 | GET / POST edit on a won and on a lost deal | refused, deal unchanged |
| EDIT-5 | 23, 20 | contact from another account; empty title | field errors next to the fields, nothing saved |
| EDIT-6 | 24 | owner changes an open lead's state from Johor to Penang | region North, owner unchanged |
| EDIT-7 | 24, 19 | another rep edits the lead; anyone edits a converted lead | 404; refused |
| EDIT-8 | 24 | rep renames an account to another account's name in different case | field error, nothing saved |
| EDIT-9 | 24 | rep edits a contact's phone from the account page | saved, shown on the account page |
| RA-1 | 25 | manager reassigns an open deal from Siti to Jason | owner Jason; Siti's open activities on it now Jason's; done ones still Siti's |
| RA-2 | 25, 19 | rep POSTs reassign | 403 |
| RA-3 | 25 | reassign a won deal; reassign to an inactive rep | refused, owner unchanged |
| DAY-4 | 26 | manager with no own deals; reps have a stale deal and a deal with no next activity | both appear on the manager's My day with their owner; team open value = sum of the team's open deals |
| DAY-5 | 26 | rep's My day | still only own deals |

## Browser (validate phase, puppeteer + Lighthouse)
- B-1: sign in as rep, open My day, tick an activity done.
- B-2: pipeline: move a card with the keyboard (select + button), then with drag and drop.
- B-3: create a quote with a 15 % line, submit, sign in as manager, approve, send, print.
- B-5: edit a deal's expected close and value from the deal page; manager reassigns it.
- B-4: responsive 1440x900 / 1024x768 / 390x844, no horizontal scroll; Lighthouse >= 90.
