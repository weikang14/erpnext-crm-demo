// AC21 for the CRM: three sizes (no horizontal scroll, 44 px controls, no console errors) and Lighthouse.
// Setup: cd CRM/scripts/ui-probe && PUPPETEER_SKIP_DOWNLOAD=1 npm install
// Session: a signed-in manager's Django sessionid in sid.txt (see the README), then: npm run probe
// Chrome: set CHROME_PATH if it isn't at the default Windows location.
// GET-only, except the AC20 form-error check: its POSTs are invalid by design (the server answers 400 and
// saves nothing), and request interception aborts any POST that isn't one of those invalid ones.
import fs from "node:fs";
import lighthouse from "lighthouse";
import puppeteer from "puppeteer-core";

const base = process.env.CRM_URL || "http://localhost:8082";
const sid = fs.readFileSync(new URL("./sid.txt", import.meta.url), "utf8").trim();
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--remote-debugging-port=9334"],
});
const page = await browser.newPage();
await browser.setCookie({ name: "sessionid", value: sid, domain: "localhost", path: "/" });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

// real records: an open deal from the board, a draft quote with lines (its editor table has the Remove column),
// a quote waiting for approval, and a won deal (its ERP order panel, 004) with its accepted quote to print
await page.goto(`${base}/pipeline/`, { waitUntil: "networkidle0" });
const openDeals = await page.$$eval(".deal-card h3 a", (as) => as.map((a) => a.href));
const deal = openDeals[0];
let draft;
for (const d of openDeals) {
  await page.goto(d);
  const drafts = await page.$$eval("tr", (rows) => rows.filter((r) => r.querySelector(".chip")?.textContent.trim() === "Draft")
    .map((r) => r.querySelector("a[href^='/quotes/']").href));
  for (const q of drafts) {
    await page.goto(q);
    if (await page.$("form[action$='/delete/']")) { draft = q; break; }
  }
  if (draft) break;
}
if (!draft) throw new Error("no draft quote with lines on an open deal: add a line to one first");
await page.goto(`${base}/approvals/`, { waitUntil: "networkidle0" });
const quote = await page.$eval("table a[href^='/quotes/']", (a) => a.href);
const firstWon = async (q) => {
  await page.goto(`${base}/deals/?stage=won${q}`, { waitUntil: "networkidle0" });
  return page.$$eval("table a[href^='/deals/']", (as) => as[0]?.href);
};
const won = (await firstWon("&q=VAL-deploy")) || (await firstWon("")); // the deploy check's sent order, if any
await page.goto(won, { waitUntil: "networkidle0" });
const accepted = await page.$eval("table a[href^='/quotes/']", (a) => a.href);
const pages = {
  home: `${base}/`, pipeline: `${base}/pipeline/`, deal, won, draft, quote, approvals: `${base}/approvals/`, print: accepted + "print/", reports: `${base}/reports/`,
  leads: `${base}/leads/`, deals: `${base}/deals/?stage=all`, enquiry: `${base}/enquiry/`,
};
const mustShow = { won: "#erp-heading" }; // the ERP order panel
let failures = 0;
for (const [name, url] of Object.entries(pages)) {
  for (const [w, h] of [[1440, 900], [1024, 768], [390, 844]]) {
    await page.setViewport({ width: w, height: h });
    errors.length = 0;
    const response = await page.goto(url, { waitUntil: "networkidle0" });
    const m = await page.evaluate((must) => {
      const controls = [...document.querySelectorAll("button, select, input:not([type=hidden]):not([type=checkbox]), .btn")]
        .filter((e) => e.offsetParent && !e.closest(".hp"));
      const small = controls.filter((e) => e.getBoundingClientRect().height < 44)
        .map((e) => `${e.tagName}:${(e.textContent || e.name || "").trim().slice(0, 20)}:${Math.round(e.getBoundingClientRect().height)}`);
      return { hScroll: document.documentElement.scrollWidth > innerWidth, small: small.slice(0, 5),
        focusMoved: document.activeElement !== document.body, missing: must && !document.querySelector(must) ? must : undefined };
    }, mustShow[name]);
    const ok = response.status() === 200 && !m.hScroll && m.small.length === 0 && errors.length === 0 && !m.focusMoved && !m.missing;
    if (!ok) failures++;
    await page.screenshot({ path: `shot-${name}-${w}x${h}.png`, fullPage: true });
    console.log(ok ? "ok  " : "FAIL", `${name} ${w}x${h}`, JSON.stringify({ status: response.status(), ...m, errors }));
  }
}

// AC20: an invalid post re-renders the record page (400) with the error beside the field. The browser must
// land on it: the first invalid field has focus and is on screen, with its error text.
await page.goto(`${base}/leads/`, { waitUntil: "networkidle0" });
let lead;
for (const href of await page.$$eval("table a[href^='/leads/']", (as) => as.map((a) => a.href))) {
  await page.goto(href);
  if (await page.$("form[action$='/disqualify/']")) { lead = href; break; }
}
if (!lead) throw new Error("no open lead with a Disqualify form");
const invalidPosts = [ // [name, page, form, make the form invalid, is this body that invalid one?]
  ["disqualify", lead, "form[action$='/disqualify/']",
    (f) => { f.elements.reason.value = ""; }, (b) => b.get("reason") === ""],
  ["deal-activity", deal, "form[action^='/activities/opportunity/']",
    (f) => { f.closest("details").open = true; f.elements.kind.value = "call"; f.elements.subject.value = "probe: call, no date";
      f.elements.due_date.value = ""; f.elements.done.checked = false; },
    (b) => b.get("kind") === "call" && b.get("due_date") === "" && !b.has("done")],
  ["deal-reassign", deal, "form[action$='/assign/']",
    (f) => { const s = f.elements.owner; s.options[s.selectedIndex].value = "999999"; }, (b) => b.get("owner") === "999999"],
];
const formPage = await browser.newPage();
await formPage.setRequestInterception(true);
let expectInvalid = () => false;
formPage.on("request", (r) => {
  if (r.method() !== "POST") return r.continue();
  if (expectInvalid(r.url(), new URLSearchParams(r.postData() || ""))) return r.continue();
  console.log("ABORTED a POST that could save:", r.url());
  r.abort();
});
for (const [name, url, form, spoil, isInvalid] of invalidPosts) {
  for (const [w, h] of [[1024, 768], [390, 844]]) {
    await formPage.setViewport({ width: w, height: h });
    await formPage.goto(url, { waitUntil: "networkidle0" });
    const action = await formPage.$eval(form, (f) => f.action);
    await formPage.$eval(form, spoil);
    expectInvalid = (u, body) => u === action && isInvalid(body);
    const [response] = await Promise.all([
      formPage.waitForNavigation({ waitUntil: "networkidle0" }), formPage.click(`${form} button[type=submit]`)]);
    expectInvalid = () => false;
    const m = await formPage.evaluate(() => {
      const el = document.activeElement, error = el.closest(".field")?.querySelector(".error");
      const inView = (e) => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; };
      const r = el.getBoundingClientRect();
      return { focused: el.id || el.tagName, ariaInvalid: el.getAttribute("aria-invalid"), top: Math.round(r.top),
        bottom: Math.round(r.bottom), fieldInView: inView(el), errorInView: !!error && inView(error), scrollY: Math.round(scrollY) };
    });
    const ok = response.status() === 400 && m.ariaInvalid === "true" && m.fieldInView && m.errorInView;
    if (!ok) failures++;
    console.log(ok ? "ok  " : "FAIL", `invalid ${name} ${w}x${h}`, JSON.stringify({ status: response.status(), ...m }));
  }
}
await formPage.close();

for (const [name, url] of [["home", pages.home], ["pipeline", pages.pipeline], ["quote", pages.quote], ["won", pages.won]]) {
  const { lhr } = await lighthouse(url, {
    port: 9334, output: "json", onlyCategories: ["performance", "accessibility", "best-practices"],
    extraHeaders: { Cookie: `sessionid=${sid}` },
  });
  const scores = Object.fromEntries(Object.entries(lhr.categories).map(([k, v]) => [k, Math.round(v.score * 100)]));
  console.log("LIGHTHOUSE", name, JSON.stringify(scores));
  if (scores.accessibility < 90 || scores["best-practices"] < 90) failures++;
  for (const a of Object.values(lhr.audits)) {
    if (a.score !== null && a.score < 0.9 && !["informative", "notApplicable", "manual"].includes(a.scoreDisplayMode)) {
      console.log("  audit below 0.9:", a.id, a.score, a.displayValue || "");
    }
  }
}
await browser.close();
console.log(failures ? `${failures} check(s) failed` : "all checks passed");
process.exitCode = failures ? 1 : 0;
