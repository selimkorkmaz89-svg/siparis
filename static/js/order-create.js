/* Dealer order screen: live product search plus an always-visible basket. */
(function () {
  "use strict";
  const config = window.ORDER_CONFIG;
  if (!config) return;

  const searchInput = document.getElementById("productSearch");
  const brandSelect = document.getElementById("brandFilter");
  const resultsBody = document.getElementById("productResults");
  const basketBody = document.getElementById("basketItems");
  const emptyRow = document.getElementById("basketEmpty");
  let timer = null;

  function money(value) {
    return Number(value).toLocaleString(config.locale, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }

  function loadProducts() {
    const params = new URLSearchParams({
      q: searchInput.value.trim(),
      brand: brandSelect ? brandSelect.value : "",
    });
    fetch(config.searchUrl + "?" + params.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { renderProducts(data.results); })
      .catch(function () { resultsBody.innerHTML = ""; });
  }

  function renderProducts(items) {
    resultsBody.innerHTML = "";
    if (!items.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="8" class="empty-state">' + config.labels.noProducts + "</td>";
      resultsBody.appendChild(row);
      return;
    }
    items.forEach(function (product) {
      const row = document.createElement("tr");
      row.innerHTML =
        "<td><code>" + product.code + "</code></td>" +
        "<td>" + product.name + "</td>" +
        "<td>" + (product.brand || "-") + "</td>" +
        '<td class="num">' + (product.tests_per_pack || "-") + "</td>" +
        '<td class="num">$' + money(product.price) + "</td>" +
        '<td class="num">%' + money(product.vat_rate) + "</td>" +
        '<td class="num"><input type="number" min="1" value="1" class="qty-input"></td>' +
        '<td><button type="button" class="btn btn-primary btn-sm">+ ' + config.labels.add + "</button></td>";
      const quantity = row.querySelector("input");
      row.querySelector("button").addEventListener("click", function () {
        addToBasket(product.id, quantity.value);
      });
      quantity.addEventListener("keydown", function (event) {
        if (event.key === "Enter") { event.preventDefault(); addToBasket(product.id, quantity.value); }
      });
      resultsBody.appendChild(row);
    });
  }

  function addToBasket(productId, quantity) {
    const body = new FormData();
    body.append("product", productId);
    body.append("quantity", quantity || 1);
    window.postForm(config.addUrl, body).then(renderBasket).catch(showError);
  }

  function showError(error) {
    window.alert(error.message || config.labels.error);
  }

  function renderBasket(data) {
    basketBody.innerHTML = "";
    if (!data.items.length) {
      emptyRow.classList.remove("hidden");
    } else {
      emptyRow.classList.add("hidden");
      data.items.forEach(function (item) {
        const row = document.createElement("tr");
        row.innerHTML =
          "<td><code>" + item.code + "</code><br><small>" + item.name + "</small></td>" +
          '<td class="num"><input type="number" min="0" value="' + item.quantity + '" class="qty-input"></td>' +
          '<td class="num">$' + money(item.unit_price) + "</td>" +
          '<td class="num">$' + money(item.line_total) + "</td>" +
          '<td><button type="button" class="btn btn-ghost btn-sm">✕</button></td>';
        const quantity = row.querySelector("input");
        quantity.addEventListener("change", function () {
          const body = new FormData();
          body.append("quantity", quantity.value);
          window.postForm(config.updateUrl.replace("0", item.id), body)
            .then(renderBasket).catch(showError);
        });
        row.querySelector("button").addEventListener("click", function () {
          window.postForm(config.removeUrl.replace("0", item.id), new FormData())
            .then(renderBasket).catch(showError);
        });
        basketBody.appendChild(row);
      });
    }
    document.getElementById("basketSubtotal").textContent = "$" + money(data.subtotal);
    document.getElementById("basketVat").textContent = "$" + money(data.vat_total);
    document.getElementById("basketTotal").textContent = "$" + money(data.total);
    const submit = document.getElementById("submitOrder");
    if (submit) submit.classList.toggle("hidden", data.count === 0);
  }

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(loadProducts, 200);
    });
  }
  if (brandSelect) brandSelect.addEventListener("change", loadProducts);
  loadProducts();
})();
