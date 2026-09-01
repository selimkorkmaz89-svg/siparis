/* Shared front-end behaviour: no build step, no framework. */
(function () {
  "use strict";

  function csrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    if (match) return match[1];
    const input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }
  window.csrfToken = csrfToken;

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: data,
    }).then(function (response) {
      if (!response.ok) return response.json().then(function (b) { throw new Error(b.error || "error"); });
      return response.json();
    });
  }
  window.postForm = post;

  /* ---- mobile menu ---- */
  const toggle = document.getElementById("menuToggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      document.getElementById("sidebar").classList.toggle("open");
    });
  }

  /* ---- highlight the active menu entry ---- */
  document.querySelectorAll(".menu a").forEach(function (link) {
    if (link.getAttribute("href") === window.location.pathname) link.classList.add("active");
  });

  /* ---- notification bell ---- */
  const bell = document.getElementById("notificationBell");
  if (bell) {
    const panel = document.getElementById("notificationPanel");
    bell.querySelector(".bell-button").addEventListener("click", function (event) {
      event.stopPropagation();
      panel.classList.toggle("hidden");
    });
    document.addEventListener("click", function (event) {
      if (!bell.contains(event.target)) panel.classList.add("hidden");
    });
    bell.querySelectorAll(".notification-link").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        const id = link.dataset.notification;
        const target = link.getAttribute("data-url") || "";
        post("/notifications/" + id + "/read/", new FormData()).finally(function () {
          window.location.href = target || link.getAttribute("href");
        });
      });
    });
  }

  /* ---- live search on list screens (no page reload while typing) ---- */
  document.querySelectorAll("form[data-live-search]").forEach(function (form) {
    const input = form.querySelector('input[type="search"]');
    if (!input) return;
    let timer = null;
    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        const table = document.querySelector("[data-filterable]");
        if (!table) return;
        const term = input.value.trim().toLocaleLowerCase();
        table.querySelectorAll("tbody tr").forEach(function (row) {
          row.classList.toggle("hidden", term !== "" && row.textContent.toLocaleLowerCase().indexOf(term) === -1);
        });
      }, 150);
    });
  });

  /* ---- confirm destructive actions ---- */
  document.querySelectorAll("[data-confirm]").forEach(function (element) {
    element.addEventListener("click", function (event) {
      if (!window.confirm(element.getAttribute("data-confirm"))) event.preventDefault();
    });
  });

  /* ---- select-all checkbox ---- */
  document.querySelectorAll("[data-check-all]").forEach(function (master) {
    master.addEventListener("change", function () {
      document
        .querySelectorAll(master.getAttribute("data-check-all"))
        .forEach(function (box) { box.checked = master.checked; });
    });
  });
})();
