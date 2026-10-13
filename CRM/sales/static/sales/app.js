// Ombak CRM: small progressive enhancements. Every page works without this file.
(function () {
  "use strict";

  // an invalid post comes back as the same page with errors beside the fields: take keyboard and eyes to the
  // first one (its aria-describedby makes screen readers read the error). The scroll is instant, never smooth.
  var invalid = document.querySelector("form [aria-invalid='true']");
  if (invalid) {
    invalid.focus({ preventScroll: true });
    invalid.scrollIntoView({ block: "center" });
  }

  // a submit button says it is working and can't be pressed twice
  document.addEventListener("submit", function (event) {
    var button = event.submitter;
    if (!button || button.hasAttribute("data-busy")) return;
    window.setTimeout(function () {
      button.setAttribute("data-busy", "");
      button.disabled = true;
    }, 0);
  });

  // print button on the quotation page (Ctrl+P works too)
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-print]")) window.print();
  });

  // pipeline board: dropping a card on a column submits the card's own "Move to" form,
  // so drag and drop goes through exactly the same server-side stage rules as the keyboard path
  var dragged = null;
  document.addEventListener("dragstart", function (event) {
    var card = event.target.closest && event.target.closest(".deal-card");
    if (!card) return;
    dragged = card;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.getAttribute("aria-labelledby") || "deal");
  });
  document.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("is-dragging");
    dragged = null;
    document.querySelectorAll(".column.is-over").forEach(function (column) {
      column.classList.remove("is-over");
    });
  });
  document.querySelectorAll(".board .column").forEach(function (column) {
    column.addEventListener("dragover", function (event) {
      if (!dragged) return;
      event.preventDefault();
      column.classList.add("is-over");
    });
    column.addEventListener("dragleave", function (event) {
      if (!column.contains(event.relatedTarget)) column.classList.remove("is-over");
    });
    column.addEventListener("drop", function (event) {
      event.preventDefault();
      column.classList.remove("is-over");
      if (!dragged) return;
      var form = dragged.querySelector(".moveform");
      var select = form.querySelector("select");
      if (select.value === column.getAttribute("data-stage")) return;
      select.value = column.getAttribute("data-stage");
      column.querySelector(".cards").appendChild(dragged);
      form.requestSubmit();
    });
  });
})();
