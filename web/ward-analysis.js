(() => {
  const areaId = new URLSearchParams(location.search).get("id") || "";
  const $ = (selector) => document.querySelector(selector);

  function formatNumber(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  }

  function formatMetric(metric) {
    const value = metric?.value;
    const unit = metric?.unit || "";
    if (value === null || value === undefined) return "—";
    if (unit === "%") return `${formatNumber(value, 1)}%`;
    if (unit === "円/㎡") return `${formatNumber(value, 0)}円/㎡`;
    if (unit === "千円") return `${formatNumber(value, 0)}千円`;
    if (unit === "千円/人") return `${formatNumber(value, 1)}千円/人`;
    if (unit === "㎡") return `${formatNumber(value, 1)}㎡`;
    if (unit === "m") return `${formatNumber(value, 1)}m`;
    if (unit === "年") return `${formatNumber(value, 1)}年`;
    if (unit === "人") return `${formatNumber(value, 0)}人`;
    if (unit === "件") return `${formatNumber(value, 0)}件`;
    if (unit === "指数") return formatNumber(value, 3);
    return `${formatNumber(value, 2)}${unit}`;
  }

  function latestByMetric(rows) {
    const grouped = new Map();
    for (const row of rows || []) {
      const previous = grouped.get(row.metric_key);
      if (!previous || String(row.period) >= String(previous.period)) grouped.set(row.metric_key, row);
    }
    return [...grouped.values()];
  }

  function metricRow(metric) {
    const sample = metric.sample_size === null || metric.sample_size === undefined ? "" : ` / n=${metric.sample_size}`;
    const quality = metric.quality_grade ? `<span class="quality-badge quality-${metric.quality_grade}">${metric.quality_grade}</span>` : "";
    return `<div class="analysis-metric-row" title="${metric.description || ""}">
      <div><span>${metric.label}</span><small>${metric.period || "—"}${sample}</small></div>
      <div class="analysis-value"><strong>${formatMetric(metric)}</strong>${quality}</div>
    </div>`;
  }

  function renderMetricCategory(selector, rows, emptyText) {
    const target = $(selector);
    if (!target) return;
    const latest = latestByMetric(rows);
    target.innerHTML = latest.length
      ? latest.map(metricRow).join("")
      : `<div class="data-missing">${emptyText}</div>`;
  }

  function renderExposures(rows) {
    const target = $("#analysis-exposures");
    if (!target) return;
    const latest = (rows || []).filter((row) => String(row.period) === "2025");
    if (!latest.length) {
      target.innerHTML = `<div class="data-missing">都市計画・防災レイヤーは拡張データ更新後に表示されます。</div>`;
      return;
    }
    const categoryLabels = { hazard: "防災", urban: "都市計画", environment: "環境", community: "生活圏" };
    target.innerHTML = latest.map((row) => {
      const isHazard = row.category === "hazard";
      const primary = isHazard ? row.population_share : row.mesh_share;
      const primaryLabel = isHazard ? "2025人口曝露" : "250mメッシュ対象率";
      return `<div class="exposure-row">
        <div class="exposure-title">
          <span>${categoryLabels[row.category] || "空間情報"}</span>
          <strong>${row.title || row.layer_key}</strong>
          <small>${row.source_vintage || ""}</small>
        </div>
        <div class="exposure-value"><strong>${primary === null || primary === undefined ? "—" : `${formatNumber(primary, 1)}%`}</strong><span>${primaryLabel}</span></div>
      </div>`;
    }).join("");
  }

  async function init() {
    if (!/^\d{5}$/.test(areaId)) return;
    try {
      const response = await fetch(`./data/analysis/ward/${areaId}.json`, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json();
      renderMetricCategory("#analysis-market", payload.metrics?.market, "詳細取引属性は次回データ更新後に表示されます。");
      renderMetricCategory("#analysis-migration", payload.metrics?.migration, "人口移動統計は拡張データ更新後に表示されます。");
      renderMetricCategory("#analysis-economy", payload.metrics?.economy, "所得・財政統計は拡張データ更新後に表示されます。");
      renderExposures(payload.exposures);
    } catch (error) {
      ["#analysis-market", "#analysis-migration", "#analysis-economy", "#analysis-exposures"].forEach((selector) => {
        const target = $(selector);
        if (target) target.innerHTML = `<div class="data-missing">詳細分析データはまだ生成されていません。</div>`;
      });
      console.info("extended analysis unavailable", error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
