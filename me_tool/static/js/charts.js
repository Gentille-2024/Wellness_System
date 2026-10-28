// Draws every <canvas data-chart="id-of-a-json-script"> with Chart.js.
// The JSON: { type, labels, datasets: [{ label, data, type?, axis?: "money" }], money?, stacked? }
(function () {
  "use strict";

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const palette = () => [1, 2, 3, 4, 5].map((i) => css(`--chart-${i}`));
  const rwf = (value) => `RWF ${Math.round(value).toLocaleString()}`;

  function build(canvas) {
    const source = document.getElementById(canvas.dataset.chart);
    if (!source || typeof Chart === "undefined") return;
    const spec = JSON.parse(source.textContent);
    const colors = palette();
    const text = css("--muted");
    const grid = css("--chart-grid");
    const isRound = spec.type === "doughnut" || spec.type === "pie";
    const hasMoneyAxis = spec.datasets.some((d) => d.axis === "money");

    const datasets = spec.datasets.map((d, i) => {
      const color = d.color ? css(d.color) || d.color : colors[i % colors.length];
      const type = d.type || spec.type;
      return {
        label: d.label,
        data: d.data,
        type,
        yAxisID: d.axis === "money" ? "money" : "y",
        backgroundColor: isRound ? d.data.map((_, j) => colors[j % colors.length]) : type === "line" ? color : color + "cc",
        borderColor: isRound ? css("--surface") : color,
        borderWidth: type === "line" ? 2.5 : isRound ? 2 : 0,
        borderDash: d.dashed ? [6, 4] : undefined,
        pointRadius: type === "line" ? 3 : 0,
        tension: 0.3,
        borderRadius: type === "bar" ? 6 : 0,
        spanGaps: true,
        order: type === "line" ? 0 : 1,
      };
    });

    const scales = isRound
      ? {}
      : {
          x: { stacked: !!spec.stacked, grid: { display: false }, ticks: { color: text, maxRotation: 0, autoSkip: true } },
          y: {
            stacked: !!spec.stacked,
            beginAtZero: true,
            grid: { color: grid },
            ticks: { color: text, precision: 0, callback: (v) => (spec.money ? rwf(v) : v.toLocaleString()) },
          },
          ...(hasMoneyAxis
            ? { money: { position: "right", beginAtZero: true, grid: { display: false }, ticks: { color: text, callback: rwf } } }
            : {}),
        };

    new Chart(canvas, {
      type: spec.type,
      data: { labels: spec.labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: spec.horizontal ? "y" : "x",
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: spec.legend !== false, labels: { color: text, boxWidth: 12, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const value = ctx.parsed.y ?? ctx.parsed;
                const money = spec.money || ctx.dataset.yAxisID === "money";
                return `${ctx.dataset.label}: ${value == null ? "—" : money ? rwf(value) : value.toLocaleString()}`;
              },
            },
          },
        },
        scales: spec.horizontal && !isRound ? { x: scales.y, y: { ...scales.x, ticks: { color: text, autoSkip: false } } } : scales,
      },
    });
  }

  function init(root) {
    root.querySelectorAll("canvas[data-chart]:not([data-ready])").forEach((canvas) => {
      canvas.dataset.ready = "1";
      build(canvas);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    init(document);
    const toggle = document.querySelector(".menu-toggle");
    if (toggle) toggle.addEventListener("click", () => document.querySelector(".nav").classList.toggle("open"));
  });
  document.addEventListener("htmx:afterSwap", (event) => init(event.target));
})();
