# UI state sequences: 004 deal ERP status

**Entity:** the deal's ERP status (`not sent` → `failed` → `sent`). There is no create, duplicate or delete of
the status itself, so the CRUD template's duplicate and delete sequences are N/A. They become the state-change
and isolation sequences below.

**Tool:** Playwright MCP or gstack `/qa-only`, clicking through the real UI. The setup is the same as in
`browser-flows.md`: the CRM runs with the override against `contract.localhost`; ERPNext is "down" with
`cd ERP && docker compose stop backend` and "up" with `start backend`.

**Views compared in every step:**
- (a) the deal's "ERP order" panel;
- (b) the number of rows in My day's "ERP orders not created" panel, for siti and for hafiz;
- (c) the deal's row in the deal list (`/deals/?stage=won`): stage and amount;
- (d) the Reports win rate and won-in-quarter value.

The contract gives the deal list no ERP column, so (c) checks only that stage and amount never move.

## UST-004-1: not sent → failed → resend → sent
1. Pick a won deal from before 004 that belongs to siti (status not sent). Note siti's My day rows S0 and
   hafiz's H0, the list row (Won, MYR X), and the reports (R).
2. VERIFY that (a) shows a grey "not sent" chip with a send form.
3. With ERPNext down, click **Send** (default date). VERIFY:
   - (a) shows a red "failed" chip with the T1 reason;
   - (b) is siti S0 + 1 and hafiz H0 + 1;
   - (c) is still Won, MYR X;
   - (d) is still R.
4. With ERPNext up, click **Send again**. VERIFY:
   - (a) shows a green "sent" chip, the order link (`…/app/sales-order/<name>`) and the new attempt time, and
     no form;
   - (b) is back to siti S0 and hafiz H0 (the panel is hidden when that is 0);
   - (c) and (d) are unchanged.
5. In ERPNext, look the order up by `crm_reference` = the quote number. VERIFY exactly 1 order.

## UST-004-2: Won with ERPNext down, then up, then resend
1. Note the My day "won this month" figure (W) and S0/H0. ERPNext is down.
2. Mark a fresh deal Q won (default date). VERIFY:
   - the response comes within 11 s with the Won flash and the T1 warning;
   - the deal is Won and W has increased by 1 deal / MYR 235.88;
   - (a) is failed;
   - (b) is S0 + 1 and H0 + 1.
3. Bring ERPNext up and reload the deal. VERIFY that it is still failed: no automatic retry, no background
   change.
4. Click **Send again**. VERIFY:
   - (a) is sent;
   - (b) is S0 and H0;
   - W is unchanged by the resend;
   - ERPNext holds exactly 1 order for the reference, with net total 235.88 and grand total 259.47.

## UST-004-3: two tabs resend the same deal
1. Fail a deal (ERPNext down), then bring ERPNext up.
2. Open the deal in tab A and tab B as siti. Both show **Send again**.
3. Submit A, then B straight after (or both at once from the page-script tool). VERIFY:
   - A gets the success flash;
   - B gets "This deal's order is already in ERPNext." if A had finished, or is refused while A is still
     `sending`;
   - no second order exists.
4. Reload both tabs. VERIFY the same order name and attempt time in each.
5. VERIFY ERPNext holds exactly 1 order for the reference, and siti's My day count is S0.

## UST-004-4: owner and manager both see it
1. Fail one of siti's deals.
2. As siti, VERIFY that (a) shows failed with a form and that (b) lists the deal.
3. As hafiz, VERIFY the same deal is on his My day and that its page shows failed with a form.
4. As jason, VERIFY the deal page is a 404 and the deal isn't on his My day.
5. hafiz clicks **Send again**. VERIFY that (a) is sent for hafiz.
6. siti reloads. VERIFY the same order name and time, with no form. VERIFY the deal is gone from siti's and
   hafiz's My day.
7. siti tries to resend through the old form, from a tab opened before step 5. VERIFY the flash "This deal's
   order is already in ERPNext." and that ERPNext still holds 1 order.

## UST-004-5: isolation between two failed deals
1. With ERPNext down, fail deal F1 (siti) and deal F2 (siti). Note F2's reason and time. (b) is S0 + 2.
2. With ERPNext up, resend F1 only. VERIFY:
   - F1 is sent;
   - F2 is still failed, with the same reason and time;
   - (b) is S0 + 1 and lists only F2;
   - both deals' list rows are unchanged.
