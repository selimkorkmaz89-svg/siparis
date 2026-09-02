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

  /* ---- mobile drawer ---- */
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("drawerBackdrop");
  function setDrawer(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    document.body.style.overflow = open ? "hidden" : "";
  }
  const toggle = document.getElementById("menuToggle");
  if (toggle) toggle.addEventListener("click", function () { setDrawer(true); });
  const closeButton = document.getElementById("drawerClose");
  if (closeButton) closeButton.addEventListener("click", function () { setDrawer(false); });
  if (backdrop) backdrop.addEventListener("click", function () { setDrawer(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setDrawer(false);
  });

  /* ---- notification bell (rendered once per breakpoint) ---- */
  document.querySelectorAll("[data-bell]").forEach(function (bell) {
    const panel = bell.querySelector("[data-bell-panel]");
    const button = bell.querySelector(".bell-button");
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      const open = panel.classList.toggle("hidden") === false;
      button.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (event) {
      if (!bell.contains(event.target)) {
        panel.classList.add("hidden");
        button.setAttribute("aria-expanded", "false");
      }
    });
  });

  /* ---- follow a notification, marking it read on the way ---- */
  document.querySelectorAll(".notification-link").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      const target = link.getAttribute("href");
      post("/notifications/" + link.dataset.notification + "/read/", new FormData())
        .catch(function () { /* marking it read is best effort */ })
        .finally(function () { window.location.href = target; });
    });
  });

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

  /* ---- second confirmation dialog before an irreversible submit ----
     Several triggers (e.g. one "Delete" button per table row) can share the
     same dialog element, so state (which form to submit, whether the click
     was already confirmed) is tracked per dialog rather than per trigger -
     otherwise confirming one row would resubmit every row's form at once. */
  const confirmDialogs = new Map();
  document.querySelectorAll("[data-confirm-dialog]").forEach(function (trigger) {
    const dialogId = trigger.getAttribute("data-confirm-dialog");
    const dialog = document.getElementById(dialogId);
    if (!dialog) return;

    let state = confirmDialogs.get(dialogId);
    if (!state) {
      state = { dialog: dialog, pendingForm: null, pendingTrigger: null };
      confirmDialogs.set(dialogId, state);

      function close() {
        dialog.classList.add("hidden");
        document.body.style.overflow = "";
        if (state.pendingTrigger) state.pendingTrigger.focus();
        state.pendingForm = null;
        state.pendingTrigger = null;
      }
      dialog.querySelectorAll("[data-modal-cancel]").forEach(function (button) {
        button.addEventListener("click", close);
      });
      dialog.addEventListener("click", function (event) {
        if (event.target === dialog) close();
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !dialog.classList.contains("hidden")) close();
      });
      const accept = dialog.querySelector("[data-modal-confirm]");
      if (accept) {
        accept.addEventListener("click", function () {
          const form = state.pendingForm;
          const pendingTrigger = state.pendingTrigger;
          dialog.classList.add("hidden");
          document.body.style.overflow = "";
          state.pendingForm = null;
          state.pendingTrigger = null;
          if (form) {
            // requestSubmit(trigger) - not plain submit() - so a button's own
            // formaction/formmethod (used to target one row's delete URL from
            // a table-wide form) is honoured instead of the form's default.
            if (form.requestSubmit && pendingTrigger) form.requestSubmit(pendingTrigger);
            else form.submit();
          } else if (pendingTrigger) {
            // No enclosing form (e.g. a plain link): replay the click, but
            // mark it so the trigger's own listener lets it through instead
            // of reopening the dialog.
            pendingTrigger.dataset.confirmDialogBypass = "1";
            pendingTrigger.click();
          }
        });
      }
    }

    trigger.addEventListener("click", function (event) {
      if (trigger.dataset.confirmDialogBypass) {
        delete trigger.dataset.confirmDialogBypass;
        return;
      }
      event.preventDefault();
      state.pendingForm = trigger.closest("form");
      state.pendingTrigger = trigger;
      dialog.classList.remove("hidden");
      document.body.style.overflow = "hidden";
      const accept = dialog.querySelector("[data-modal-confirm]");
      if (accept) accept.focus();
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

  /* ---- show only the field group matching a select's current value ---- */
  document.querySelectorAll("[data-provider-toggle]").forEach(function (container) {
    const select = document.getElementById(container.getAttribute("data-provider-toggle"));
    if (!select) return;
    const groups = container.querySelectorAll("[data-provider-group]");
    function apply() {
      groups.forEach(function (group) {
        group.classList.toggle(
          "hidden", group.getAttribute("data-provider-group") !== select.value
        );
      });
    }
    select.addEventListener("change", apply);
    apply();
  });

  /* ---- dual listbox: a searchable two-column picker for a <select multiple> ----
     The real select stays in the DOM (hidden) so the form submits exactly as
     before; this only changes how picking options feels. */
  document.querySelectorAll("select[multiple][data-dual-listbox]").forEach(function (select) {
    const data = select.dataset;
    const wrap = document.createElement("div");
    wrap.className = "dual-listbox";
    wrap.innerHTML =
      '<div class="dual-listbox-col">' +
        '<div class="dual-listbox-col-head"><span>' + data.dualListboxAvailableLabel + "</span></div>" +
        '<input type="search" class="dual-listbox-search" placeholder="' + data.dualListboxSearchPlaceholder + '">' +
        '<ul class="dual-listbox-list" data-side="available"></ul>' +
      "</div>" +
      '<div class="dual-listbox-col">' +
        '<div class="dual-listbox-col-head"><span>' + data.dualListboxSelectedLabel +
          ' (<span data-count>0</span>)</span>' +
          '<button type="button" class="dual-listbox-clear">' + data.dualListboxClearLabel + "</button>" +
        "</div>" +
        '<ul class="dual-listbox-list" data-side="selected"></ul>' +
      "</div>";
    select.insertAdjacentElement("afterend", wrap);
    select.classList.add("hidden");

    const availableList = wrap.querySelector('[data-side="available"]');
    const selectedList = wrap.querySelector('[data-side="selected"]');
    const search = wrap.querySelector(".dual-listbox-search");
    const clearBtn = wrap.querySelector(".dual-listbox-clear");
    const countEl = wrap.querySelector("[data-count]");

    function row(option, glyph, onClick) {
      const li = document.createElement("li");
      li.className = "dual-listbox-item";
      li.tabIndex = 0;
      const label = document.createElement("span");
      label.textContent = option.text;
      const icon = document.createElement("span");
      icon.className = "move-icon";
      icon.textContent = glyph;
      li.append(label, icon);
      li.addEventListener("click", onClick);
      li.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      });
      return li;
    }

    function empty(list, text) {
      const li = document.createElement("li");
      li.className = "dual-listbox-empty";
      li.textContent = text;
      list.appendChild(li);
    }

    function render() {
      const term = search.value.trim().toLocaleLowerCase();
      availableList.innerHTML = "";
      selectedList.innerHTML = "";
      let selectedCount = 0;
      Array.from(select.options).forEach(function (option) {
        if (option.selected) {
          selectedCount++;
          selectedList.appendChild(row(option, "✕", function () {
            option.selected = false;
            select.dispatchEvent(new Event("change"));
            render();
          }));
        } else if (!term || option.text.toLocaleLowerCase().indexOf(term) !== -1) {
          availableList.appendChild(row(option, "+", function () {
            option.selected = true;
            select.dispatchEvent(new Event("change"));
            render();
          }));
        }
      });
      if (!availableList.children.length) empty(availableList, data.dualListboxEmptyLabel);
      if (!selectedList.children.length) empty(selectedList, data.dualListboxNoneSelectedLabel);
      countEl.textContent = selectedCount;
      clearBtn.disabled = selectedCount === 0;
    }

    search.addEventListener("input", render);
    clearBtn.addEventListener("click", function () {
      Array.from(select.selectedOptions).forEach(function (option) { option.selected = false; });
      select.dispatchEvent(new Event("change"));
      render();
    });
    render();
  });
})();
