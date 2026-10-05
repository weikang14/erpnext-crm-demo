// AC13 (sizes, no h-scroll, tap targets) and AC16 (Lighthouse) for the shop-floor terminal.
// Setup: cd ERP/scripts/ui-probe && PUPPETEER_SKIP_DOWNLOAD=1 npm install
// Session: put an operator's Django sessionid in sid.txt (see the README), then: npm run probe
// Chrome: set CHROME_PATH if it isn't at the default Windows location.
import fs from "node:fs";
import lighthouse from "lighthouse";
import puppeteer from "puppeteer-core";

const sid = fs.readFileSync(new URL("./sid.txt", import.meta.url), "utf8").trim();
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--remote-debugging-port=9333"],
});
const page = await browser.newPage();
await browser.setCookie({ name: "sessionid", value: sid, domain: "localhost", path: "/" });

// the complete page of whichever open card is first in the queue (demo cards get completed over time)
const queueUrl = `http://localhost:8081/?workstation=${encodeURIComponent(process.env.STATION || "Welding Bay")}`;
await page.goto(queueUrl, { waitUntil: "networkidle0" });
const firstCard = await page.$eval(".card__id", (el) => el.textContent.trim());
const pages = { queue: queueUrl, complete: `http://localhost:8081/job/${firstCard}/complete/` };
console.log("pages", JSON.stringify(pages));
for (const [name, url] of Object.entries(pages)) {
  for (const [w, h] of [[390, 844], [768, 1024], [1024, 768]]) {
    await page.setViewport({ width: w, height: h });
    await page.goto(url, { waitUntil: "networkidle0" });
    const m = await page.evaluate(() => {
      const r = (el) => el.getBoundingClientRect();
      const taps = [...document.querySelectorAll("button, a, select, input:not([type=hidden])")].filter((e) => e.offsetParent);
      const primary = [...document.querySelectorAll(".btn--start,.btn--pause,.btn--complete,.btn--primary")];
      let minGap = Infinity;
      for (const a of taps) for (const b of taps) {
        if (a === b || a.contains(b) || b.contains(a)) continue;
        const A = r(a), B = r(b);
        const overlapX = Math.min(A.right, B.right) > Math.max(A.left, B.left);
        const overlapY = Math.min(A.bottom, B.bottom) > Math.max(A.top, B.top);
        const dx = Math.max(A.left, B.left) - Math.min(A.right, B.right);
        const dy = Math.max(A.top, B.top) - Math.min(A.bottom, B.bottom);
        if (overlapX && dy >= 0 && dy < 40) minGap = Math.min(minGap, dy);
        if (overlapY && dx >= 0 && dx < 40) minGap = Math.min(minGap, dx);
      }
      const smallest = taps
        .map((e) => [e.textContent.trim().slice(0, 14) || e.name || e.tagName, Math.round(r(e).width), Math.round(r(e).height)])
        .sort((a, b) => Math.min(a[1], a[2]) - Math.min(b[1], b[2]))[0];
      return {
        hScroll: document.documentElement.scrollWidth > innerWidth,
        primaryMinHeight: primary.length ? Math.min(...primary.map((b) => Math.round(r(b).height))) : null,
        smallestTap: smallest,
        minGap: minGap === Infinity ? null : Math.round(minGap),
      };
    });
    await page.screenshot({ path: `shot-${name}-${w}x${h}.png`, fullPage: true });
    console.log(`${name} ${w}x${h}`, JSON.stringify(m));
  }
}

const { lhr } = await lighthouse(pages.queue, {
  port: 9333,
  output: "json",
  onlyCategories: ["performance", "accessibility", "best-practices"],
  extraHeaders: { Cookie: `sessionid=${sid}` },
});
console.log("LIGHTHOUSE", JSON.stringify(Object.fromEntries(Object.entries(lhr.categories).map(([k, v]) => [k, Math.round(v.score * 100)]))));
for (const a of Object.values(lhr.audits)) {
  if (a.score !== null && a.score < 0.9 && !["informative", "notApplicable", "manual"].includes(a.scoreDisplayMode)) {
    console.log("audit below 0.9:", a.id, a.score, a.displayValue || "");
  }
}
fs.writeFileSync("lighthouse-queue.json", JSON.stringify(lhr));
await browser.close();
