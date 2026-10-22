/* Gráficos locais, sem CDN e sem script inline (compatível com CSP). */
(function () {
  "use strict";

  function parseData(canvas, name, fallback) {
    var raw = canvas.dataset[name];
    if (!raw) return fallback;
    try {
      return JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  }

  function setup(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.parentElement.getBoundingClientRect();
    var width = Math.max(320, rect.width || 640);
    var height = Number(canvas.getAttribute("height")) || 220;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    return { ctx: ctx, width: width, height: height };
  }

  function drawEmpty(ctx, width, height) {
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#6b7069";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Sem dados para o período.", width / 2, height / 2);
  }

  function drawBars(canvas, labels, series) {
    var size = setup(canvas);
    var ctx = size.ctx;
    var width = size.width;
    var height = size.height;
    if (!labels.length || !series.length) {
      drawEmpty(ctx, width, height);
      return;
    }

    var padding = { top: 18, right: 14, bottom: 44, left: 54 };
    var chartW = width - padding.left - padding.right;
    var chartH = height - padding.top - padding.bottom;
    var values = [];
    series.forEach(function (item) {
      item.values.forEach(function (value) {
        values.push(Number(value) || 0);
      });
    });
    var max = Math.max.apply(null, values.concat([0]));
    var min = Math.min.apply(null, values.concat([0]));
    var span = max - min || 1;
    var zeroY = padding.top + (max / span) * chartH;
    var slot = chartW / labels.length;
    var barW = Math.max(3, (slot * 0.72) / series.length);

    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#c9c3b6";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(width - padding.right, zeroY);
    ctx.stroke();

    labels.forEach(function (label, index) {
      var x = padding.left + index * slot + slot * 0.14;
      series.forEach(function (item, serieIndex) {
        var value = Number(item.values[index]) || 0;
        var barH = (Math.abs(value) / span) * chartH;
        var y = value >= 0 ? zeroY - barH : zeroY;
        ctx.fillStyle = item.color || "#2f6b4f";
        ctx.fillRect(x + serieIndex * barW, y, Math.max(2, barW - 2), barH);
      });
      if (labels.length <= 12 || index % Math.ceil(labels.length / 8) === 0) {
        ctx.save();
        ctx.translate(padding.left + index * slot + slot / 2, height - 22);
        ctx.rotate(-0.45);
        ctx.fillStyle = "#4b514b";
        ctx.font = "11px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(String(label), 0, 0);
        ctx.restore();
      }
    });

    ctx.fillStyle = "#4b514b";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(String(max), padding.left - 6, padding.top + 4);
    ctx.fillText(String(min), padding.left - 6, padding.top + chartH);

    if (series.length > 1) {
      var legendX = padding.left;
      series.forEach(function (item) {
        ctx.fillStyle = item.color || "#2f6b4f";
        ctx.fillRect(legendX, 4, 10, 10);
        ctx.fillStyle = "#4b514b";
        ctx.textAlign = "left";
        ctx.fillText(item.label, legendX + 14, 13);
        legendX += ctx.measureText(item.label).width + 34;
      });
    }
  }

  function init() {
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var labels = parseData(canvas, "labels", []);
      if (canvas.dataset.chart === "grouped") {
        var series = parseData(canvas, "series", []);
        drawBars(canvas, labels, series);
      } else {
        var values = parseData(canvas, "values", []);
        drawBars(canvas, labels, [
          { label: "Receita", color: "#2f6b4f", values: values },
        ]);
      }
    });
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(init, 120);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
