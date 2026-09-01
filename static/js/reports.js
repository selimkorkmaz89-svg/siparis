/* Reporting charts (Chart.js). Data arrives via json_script from the view. */
(function () {
  "use strict";
  const node = document.getElementById("chartData");
  if (!node || typeof Chart === "undefined") return;
  const data = JSON.parse(node.textContent);
  const BRAND = "#0D8DBE";
  const PALETTE = ["#0D8DBE", "#0a6f96", "#38bdf8", "#0ea5e9", "#22c55e",
                   "#f59e0b", "#8b5cf6", "#ef4444", "#14b8a6", "#64748b"];

  function bar(canvasId, series, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !series || !series.labels.length) return;
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: series.labels,
        datasets: [{ label: label, data: series.values, backgroundColor: BRAND, borderRadius: 4 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function pie(canvasId, series) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !series || !series.labels.length) return;
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: series.labels,
        datasets: [{ data: series.values, backgroundColor: PALETTE }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "right" } },
      },
    });
  }

  function line(canvasId, series, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !series || !series.labels.length) return;
    new Chart(canvas, {
      type: "line",
      data: {
        labels: series.labels,
        datasets: [{
          label: label, data: series.values, borderColor: BRAND,
          backgroundColor: "rgba(13,141,190,.14)", fill: true, tension: .3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  line("trendChart", data.trend, "");
  bar("dealerChart", data.dealers, "");
  bar("productChart", data.products, "");
  pie("brandChart", data.brands);
})();
