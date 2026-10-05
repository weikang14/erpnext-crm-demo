// Ombak shop-floor terminal: progressive enhancement only; every action also works without JS.

// Station picker: changing the station loads it straight away.
document.querySelectorAll("form[data-autosubmit] select").forEach((select) => {
  select.addEventListener("change", () => select.form.submit());
});

// One tap = one request: disable the button and say so.
document.querySelectorAll("form[data-busy]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (form.dataset.sent) {
      event.preventDefault();
      return;
    }
    form.dataset.sent = "1";
    const button = event.submitter || form.querySelector("button[type=submit]");
    if (button) {
      button.disabled = true;
      button.textContent = "Working...";
    }
  });
});

// Running timers tick locally; the server sent the seconds elapsed so far.
const timers = [...document.querySelectorAll(".timer[data-elapsed]")];
const startedAt = Date.now();
const pad = (n) => String(n).padStart(2, "0");
if (timers.length) {
  setInterval(() => {
    const extra = Math.floor((Date.now() - startedAt) / 1000);
    timers.forEach((timer) => {
      const total = Number(timer.dataset.elapsed) + extra;
      timer.textContent = `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
    });
  }, 1000);
}

// Keep the queue current while nobody is touching the screen.
const queue = document.querySelector("[data-refresh]");
if (queue) {
  let lastTouch = Date.now();
  ["pointerdown", "keydown", "focusin"].forEach((name) =>
    document.addEventListener(name, () => (lastTouch = Date.now()))
  );
  const seconds = Number(queue.dataset.refresh) * 1000;
  setInterval(() => {
    const busy = document.querySelector("form[data-sent]");
    if (!busy && Date.now() - lastTouch >= seconds) window.location.reload();
  }, seconds);
}
