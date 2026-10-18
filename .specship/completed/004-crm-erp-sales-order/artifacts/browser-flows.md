# Browser flows: 004

Run in the validate phase with Playwright or Chrome DevTools MCP, or with `CRM/scripts/ui-probe`.

## Setup (all flows)
- **ERP:** `cd ERP && docker compose up -d`. Prepare `contract.localhost` with the masters and the CRM keys,
  as `CRM/scripts/test-erp.sh` does.
- **CRM:** start it with the override, pointed at the contract site so no flow writes to the demo site:
  `cd CRM && ERPNEXT_SITE=contract.localhost docker compose -f docker-compose.yml -f docker-compose.erp.yml up -d`.
  The Desk link will then open `localhost:8080`, so check its `href` rather than following it.
- **Not-configured flow:** plain `docker compose up -d`, without the override.
- **ERPNext down:** `cd ERP && docker compose stop backend`. Bring it back with `docker compose start backend`.
- **ERPNext slow:** `cd ERP && docker compose pause backend`. Connections are accepted but never answered, so
  each call waits for the 10 s timeout. Undo it with `docker compose unpause backend`.
- **App and users:** the CRM is at http://localhost:8082. Users are `siti` (rep), `jason` (another rep) and
  `hafiz` (manager), with the demo password (`CRM_DEMO_PASSWORD`).
- **Deal:** "deal Q" = a siti deal in Quotation with a sent quote of 3 × FG-CT-300 at 7.5 % (MYR 235.88).
  Make one per flow: New quote → Finish → (approve as hafiz if needed) → Mark as sent.
- **Screenshots:** viewport 1440×900 unless stated. Name them `BF<n>-<letter>`.

### BF-004-1: Won with a valid delivery date (AC1, AC3, AC6, AC17)
1. Sign in as siti and open deal Q.
2. Verify the Won form shows a "Requested delivery date" input of `type=date`, with its value = today + 14
   (KL) and `min` = today, next to "Mark won". **[BF1-a]**
3. Keep the default and click **Mark won**.
4. Verify these appear at the top: "Won: <title>, MYR 235.88." and "Sales order SAL-ORD-… created in ERPNext.".
   **[BF1-b]**
5. Verify the "ERP order" panel shows a green "sent" chip and the order name as a link whose `href` is
   `http://localhost:8080/app/sales-order/<name>`, with the date and time of the last attempt in KL. There is no send form. "Won on <date>." shows,
   with no Move, Won, Edit or Lost controls. **[BF1-c]**
- **Pass:** all of the above.
- **Fail:** a 500 page, no ERP flash, a grey or red chip, or a send form on a sent deal.

### BF-004-2: Won with a past date (AC1, FM14)
1. Open a fresh deal Q. Set the date to yesterday and click **Mark won**.
2. Verify the browser's native validation blocks the submit (`min`). **[BF2-a]**
3. Remove `min` and `required` from the input with the page-script tool, then submit yesterday's date again.
4. Verify the deal page re-renders with HTTP 400 and the error sits directly under the date field. Focus is on
   the date input, and it is scrolled into view at 1024×768 and at 390×844. **[BF2-b]**
5. Reload. Verify the deal is still in Quotation and the quote is still Sent.
- **Pass:** 400, the error beside the field, focus on it, the deal still open.
- **Fail:** 302/Won, the error at the top of the page only, or focus left on the body.

### BF-004-3: Won with no date (AC1)
1. Same as BF-2, but clear the date and remove `required`, then submit.
2. Verify 400, an error beside the field and focus on the field. **[BF3-a]**
3. Verify the deal is still open.
- **Pass:** as BF-2.
- **Fail:** Won with no delivery date stored.

### BF-004-4: Failed send, reason shown, resend (AC2, AC14, AC15, AC17)
1. Stop the ERP backend, then mark a fresh deal Q won with the default date.
2. Verify the response comes within 11 s. The Won flash and a warning appear, the warning reading "ERPNext
   didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."
   **[BF4-a]**
3. Verify the panel shows a red "failed" chip, the same reason and the attempt time. It has a send form with the
   date prefilled and a **Send again** button. The deal is still Won. **[BF4-b]**
4. Start the backend. Remove `min` from the panel's date input, enter yesterday and click **Send again**.
   Verify a 400 page with the error beside the date field, the deal still failed and nothing sent. **[BF4-c0]**
   Then enter today + 20 and click **Send again**.
5. Verify the success flash, a green "sent" chip with the order link and the new attempt time, and no form.
   **[BF4-c]**
- **Pass:** Won is kept throughout, and the resend gives exactly one order.
- **Fail:** Won undone, a 500, a hang longer than 11 s, or the form still offered after the order was sent.

### BF-004-5: Not configured (AC16, AC17)
1. With the CRM running without the override, mark a fresh deal Q won.
2. Verify only the Won flash appears, with no ERP warning.
3. Verify the panel shows a grey chip reading "ERP link not configured", and that there is no send form, for
   siti and for hafiz. **[BF5-a]**
- **Pass:** Won works as in 003.
- **Fail:** an error flash, a red chip, a send form, or a delay.

### BF-004-6: My day, failed sends for a rep (AC18)
1. Leave BF-4's deal failed (backend stopped).
2. As siti, open **My day**.
3. Verify the panel "ERP orders not created" lists that deal, and that its link opens the deal page. **[BF6-a]**
4. As jason, open My day and verify the deal is not listed.
5. Resend it successfully, return to siti's My day, and verify the panel is gone. **[BF6-b]**
- **Pass:** rows appear only for failed sends, and only to their owner or the manager.
- **Fail:** sent deals listed, another rep's deal listed, or an empty panel shown.

### BF-004-7: My day, failed sends for the manager (AC18, AC15)
1. Fail one siti deal and one jason deal.
2. As hafiz, open My day and verify both deals are listed. **[BF7-a]**
3. Open siti's deal and verify the send form is there. Send it (backend up) and verify the panel is now sent.
4. Back on My day, verify only jason's deal remains. **[BF7-b]**
- **Pass:** the manager sees the whole team and can resend.
- **Fail:** the manager sees only his own deals, or gets a 404 on the send.

### BF-004-8: Keyboard only (AC17, NFR accessibility)
1. On a fresh deal Q, use only Tab, Shift+Tab, typing and Enter.
2. Reach the date field and verify a focus ring is visible. **[BF8-a]**
3. Type a date 20 days ahead, Tab to **Mark won** and press Enter.
4. On a failed deal, Tab into the panel and verify the date field and **Send again** are reachable in order,
   with focus visible. **[BF8-b]**
5. Press Enter to send.
- **Pass:** no step needs the mouse, and focus is always visible.
- **Fail:** a control can't be reached, or there is no focus indicator.

### BF-004-9: 390 px width (AC17)
1. Set the viewport to 390×844.
2. Open a won deal in each state (sent, failed, not configured) and My day with failed sends.
3. Verify `document.documentElement.scrollWidth <= 390`.
4. Verify the date input, **Mark won**, **Send again** and the order link are each at least 44 px tall.
5. Verify a long ERPNext reason (300 characters) wraps inside the panel. **[BF9-a sent, BF9-b failed, BF9-c My day]**
- **Pass:** no horizontal scroll, and every target is at least 44 px.
- **Fail:** overflow, or a clipped chip or reason.

### BF-004-10: No JavaScript (AC17, EB9)
1. Disable JavaScript.
2. Mark a fresh deal Q won with a valid date. Verify the flashes and the sent panel.
3. Submit a past date with `min` removed. Verify the 400 page shows the error beside the field. (Focus doesn't
   move without JS; that is expected.) **[BF10-a]**
4. Stop the backend, fail a deal, start the backend, then **Send again**. Verify it is sent. **[BF10-b]**
5. Verify the console shows no CSP violations, and the page source has no `on*=`, no inline `<script>` and no
   `style=`.
- **Pass:** every step works as a plain form POST.
- **Fail:** a control that needs JS, or a CSP violation.

### BF-004-11: Slow ERPNext: the sending claim, with nothing blocked (AC15)
1. Fail a fresh deal Q (backend stopped), then start the backend and pause it.
2. Open the deal in tabs A, B and C as siti. All three show **Send again**.
3. In tab A, click **Send again**. The request waits up to 10 s.
4. Within 5 s, in tab B:
   - reload the deal page and verify it loads in under 1 s;
   - log a call on the deal and verify it is saved in under 1 s. **[BF11-a]**
5. Within those same 5 s, submit tab C's **Send again** form. Verify the send is refused (the deal is
   `sending`) and no second send starts.
6. When tab A returns, verify the deal is failed with the "ERPNext didn't answer…" reason. **[BF11-b]**
7. Unpause the backend and click **Send again**. Verify the deal is sent, and that ERPNext holds exactly one
   order for the quote number.
- **Pass:** the deal page and the activity are never blocked by the pending send, and the second click is
  refused.
- **Fail:** tab B hangs until tab A finishes, or two sends run.
