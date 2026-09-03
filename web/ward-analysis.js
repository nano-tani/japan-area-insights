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
    const zeroDigitUnits = new Set(["人", "件", "戸", "施設", "床", "箇所"]);
    if (unit === "%") return `${formatNumber(value, 1)}%`;
    if (unit === "円/㎡") return `${formatNumber(value, 0)}円/㎡`;
    if (unit === "千円") return `${formatNumber(value, 0)}千円`;
    if (unit === "千円/人") return `${formatNumber(value, 1)}千円/人`;
    if (unit === "㎡") return `${formatNumber(value, 1)}㎡`;
    if (unit === "m") return `${formatNumber(value, 0)}m`;
    if (unit === "年") return `${formatNumber(value, 0)}年`;
    if (unit === "床/万人") return `${formatNumber(value, 1)}床/万人`;
    if (unit === "人/万人") return `${formatNumber(value, 1)}人/万人`;
    if (unit === "箇所/万人") return `${formatNumber(value, 2)}箇所/万人`;
    if (unit === "倍") return `${formatNumber(value, 2)}倍`;
    if (zeroDigitUnits.has(unit)) return `${formatNumber(value, 0)}${unit}`;
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

  function combine(metrics, categories) {
    return categories.flatMap((category) => metrics?.[category] || []);
  }

  function ensureSocialCards() {
    const grid = document.querySelector(".analysis-grid");
    const exposureCard = $("#analysis-exposures")?.closest(".analysis-card");
    if (!grid || !exposureCard || $("#analysis-housing")) return;
    exposureCard.insertAdjacentHTML("beforebegin", `
      <article class="analysis-card"><div class="analysis-card-head"><span>HOUSING</span><h3>住宅ストック</h3></div><div id="analysis-housing"></div></article>
      <article class="analysis-card"><div class="analysis-card-head"><span>WORK & EDUCATION</span><h3>労働・教育</h3></div><div id="analysis-work-education"></div></article>
      <article class="analysis-card"><div class="analysis-card-head"><span>HEALTH & WELFARE</span><h3>医療・福祉・文化</h3></div><div id="analysis-health-welfare"></div></article>
      <article class="analysis-card"><div class="analysis-card-head"><span>RESILIENCE</span><h3>避難・災害履歴</h3></div><div id="analysis-resilience"></div></article>
    `);
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

  function renderAll(payload) {
    ensureSocialCards();
    const metrics = payload.metrics || {};
    renderMetricCategory("#analysis-market", metrics.market, "詳細取引属性は次回データ更新後に表示されます。");
    renderMetricCategory("#analysis-migration", metrics.migration, "人口移動統計は拡張データ更新後に表示されます。");
    renderMetricCategory("#analysis-economy", metrics.economy, "所得・財政統計は拡張データ更新後に表示されます。");
    renderMetricCategory("#analysis-housing", metrics.housing, "住宅統計は拡張データ更新後に表示されます。");
    renderMetricCategory("#analysis-work-education", combine(metrics, ["labor", "education"]), "労働・教育統計は拡張データ更新後に表示されます。");
    renderMetricCategory("#analysis-health-welfare", combine(metrics, ["health", "welfare", "culture"]), "医療・福祉・文化統計は拡張データ更新後に表示されます。");
    renderMetricCategory("#analysis-resilience", metrics.resilience, "避難場所・災害履歴は拡張データ更新後に表示されます。");
    renderExposures(payload.exposures);
  }

  async function init() {
    if (!/^\d{5}$/.test(areaId)) return;
    ensureSocialCards();
    try {
      const response = await fetch(`./data/analysis/ward/${areaId}.json`, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      renderAll(await response.json());
    } catch (error) {
      [
        "#analysis-market", "#analysis-migration", "#analysis-economy",
        "#analysis-housing", "#analysis-work-education", "#analysis-health-welfare",
        "#analysis-resilience", "#analysis-exposures"
      ].forEach((selector) => {
        const target = $(selector);
        if (target) target.innerHTML = `<div class="data-missing">詳細分析データはまだ生成されていません。</div>`;
      });
      console.info("extended analysis unavailable", error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
