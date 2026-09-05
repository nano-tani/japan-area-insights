(() => {
  const shortlist = () => window.StationShortlist;
  const root = () => document.querySelector("#station-compare-root");
  let activeLens = "balanced";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function selectedCodes() {
    const maxItems = shortlist()?.MAX_ITEMS || 3;
    const query = new URLSearchParams(location.search).get("codes") || "";
    const fromQuery = query.split(",").map((value) => value.trim()).filter((value) => /^\d+$/.test(value));
    const fallback = (shortlist()?.read() || []).map((item) => String(item.code || "")).filter((value) => /^\d+$/.test(value));
    return [...new Set(fromQuery.length ? fromQuery : fallback)].slice(0, maxItems);
  }

  function metric(detail, key) {
    return detail?.metrics?.[key]?.value ?? null;
  }

  function future(detail, year) {
    return (detail?.future_population || []).find((row) => Number(row?.year) === Number(year)) || null;
  }

  function fmt(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  }

  function fmtInt(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Math.round(Number(value)).toLocaleString("ja-JP");
  }

  function propertySearchUrl(name) {
    const stationName = String(name || "").endsWith("駅") ? String(name) : `${String(name || "")}駅`;
    return `https://www.google.com/search?q=${encodeURIComponent(`${stationName} 物件 賃貸 中古マンション`)}`;
  }

  function normalizeScore(value, maximum) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
    return Math.max(0, Math.min(100, Number(value) / maximum * 100));
  }

  function average(values) {
    const usable = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)));
    return usable.length ? usable.reduce((sum, value) => sum + Number(value), 0) / usable.length : null;
  }

  function componentScores(detail) {
    const flood = metric(detail, "hazard_flood_population_share");
    const quake = metric(detail, "seismic_30y_6lower_probability");
    const risks = [flood, quake]
      .filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)))
      .map((value) => Math.max(0, Math.min(100, Number(value))));
    return {
      future: normalizeScore(detail.future_population_score, 20),
      daily: average([
        normalizeScore(detail.convenience_score, 15),
        normalizeScore(detail.transport_score, 15),
      ]),
      market: average([
        normalizeScore(detail.price_score, 20),
        normalizeScore(detail.transaction_score, 10),
      ]),
      safety: risks.length ? 100 - average(risks) : null,
    };
  }

  const COMPONENT_LABELS = {
    future: "将来人口",
    daily: "生活・交通",
    market: "価格・取引",
    safety: "水害・地震",
  };

  const LENSES = {
    balanced: {
      label: "バランス",
      weights: { future: 30, daily: 30, market: 20, safety: 20 },
      note: "将来人口30%・生活交通30%・価格取引20%・水害地震20%",
    },
    longterm: {
      label: "長く住みたい",
      weights: { future: 55, daily: 15, market: 10, safety: 20 },
      note: "将来人口55%・生活交通15%・価格取引10%・水害地震20%",
    },
    daily: {
      label: "生活・交通重視",
      weights: { future: 15, daily: 65, market: 10, safety: 10 },
      note: "将来人口15%・生活交通65%・価格取引10%・水害地震10%",
    },
    market: {
      label: "価格と将来性",
      weights: { future: 40, daily: 5, market: 55, safety: 0 },
      note: "将来人口40%・生活交通5%・価格取引55%",
    },
  };

  function lensScore(detail, lens) {
    const components = componentScores(detail);
    let weighted = 0;
    let weightTotal = 0;
    Object.entries(lens.weights).forEach(([key, weight]) => {
      const value = components[key];
      if (!weight || value === null || value === undefined) return;
      weighted += value * weight;
      weightTotal += weight;
    });
    return {
      detail,
      components,
      score: weightTotal ? weighted / weightTotal : null,
      coverage: Object.values(lens.weights).reduce((sum, weight) => sum + weight, 0)
        ? weightTotal / Object.values(lens.weights).reduce((sum, weight) => sum + weight, 0) * 100
        : 0,
    };
  }

  function stationName(detail) {
    const name = String(detail?.name || detail?.station_code || "駅");
    return name.endsWith("駅") ? name : `${name}駅`;
  }

  function renderDecisionSummary(details) {
    const lens = LENSES[activeLens] || LENSES.balanced;
    const results = details
      .map((detail) => lensScore(detail, lens))
      .filter((result) => result.score !== null)
      .sort((a, b) => b.score - a.score || String(a.detail.station_code).localeCompare(String(b.detail.station_code)));

    if (!results.length) {
      return '<section class="station-compare-summary"><div class="station-compare-summary-head"><div><span>DECISION SUMMARY</span><h2>条件別の要約</h2></div></div><p class="station-compare-summary-empty">比較に使えるスコアが不足しています。</p></section>';
    }

    const winner = results[0];
    const runnerUp = results[1] || null;
    const gap = runnerUp ? winner.score - runnerUp.score : 0;
    const topComponents = Object.entries(winner.components)
      .filter(([, value]) => value !== null && value !== undefined)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 2);
    const verdict = runnerUp && gap < 3
      ? `${stationName(winner.detail)}と${stationName(runnerUp.detail)}の差は小さめです。`
      : `${stationName(winner.detail)}が、この比較内では条件に合いやすい結果です。`;

    const options = Object.entries(LENSES).map(([key, item]) =>
      `<option value="${key}"${key === activeLens ? " selected" : ""}>${escapeHtml(item.label)}</option>`
    ).join("");
    const rows = results.map((result, index) => {
      const strong = Object.entries(result.components)
        .filter(([, value]) => value !== null && value !== undefined)
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .slice(0, 2)
        .map(([key, value]) => `${COMPONENT_LABELS[key]} ${Math.round(value)}`)
        .join(" / ");
      return `<article class="station-compare-summary-row${index === 0 ? " is-leading" : ""}">
        <div><span>#${index + 1}</span><strong>${escapeHtml(stationName(result.detail))}</strong><small>${escapeHtml(strong || "比較可能データが少なめ")}</small></div>
        <div><strong>${Math.round(result.score)}</strong><span>一致度</span><small>データ反映 ${Math.round(result.coverage)}%</small></div>
      </article>`;
    }).join("");

    return `<section class="station-compare-summary" aria-labelledby="station-decision-summary-title">
      <div class="station-compare-summary-head">
        <div><span>DECISION SUMMARY</span><h2 id="station-decision-summary-title">条件別に見る</h2></div>
        <label>重視する条件<select id="station-compare-lens">${options}</select></label>
      </div>
      <div class="station-compare-verdict"><strong>${escapeHtml(verdict)}</strong><span>${escapeHtml(lens.note)}。欠損項目は除外して残りの重みを再配分します。</span></div>
      <div class="station-compare-summary-grid">${rows}</div>
      <p class="station-compare-summary-note">これは保存した駅同士を同じ重みで比較する補助指標です。${topComponents.length ? `首位駅では ${topComponents.map(([key]) => COMPONENT_LABELS[key]).join("・")} が相対的に高めです。` : ""} 最終判断は下の実数値も確認してください。</p>
    </section>`;
  }

  const METRICS = [
    { label: "参考総合評価", value: (d) => fmt(d.total_score, 1), note: "東京23区の駅1km圏内での相対評価", unit: "/ 100" },
    { label: "2045 / 2025人口", value: (d) => fmt(metric(d, "future_population_retention_2045"), 1), note: "駅中心1km圏・250mメッシュ集計", unit: "%" },
    { label: "2025年推計人口", value: (d) => fmtInt(future(d, 2025)?.projected_population), note: "駅中心1km圏", unit: "人" },
    { label: "2045年推計人口", value: (d) => fmtInt(future(d, 2045)?.projected_population), note: "駅中心1km圏", unit: "人" },
    { label: "直近取引単価中央値", value: (d) => fmtInt(metric(d, "transaction_unit_price_median_latest")), note: "駅コード指定取引。1km圏物件を意味しない", unit: "円/㎡" },
    { label: "取引単価変化", value: (d) => fmt(metric(d, "transaction_unit_price_change"), 1), note: "駅コード指定取引の中期変化", unit: "%" },
    { label: "直近5完了年の取引", value: (d) => fmtInt(metric(d, "transaction_count_5y")), note: "駅コード指定データ", unit: "件" },
    { label: "生活施設 合計", value: (d) => {
      const keys = ["school", "childcare", "medical", "library", "public_facility"];
      const values = keys.map((key) => metric(d, `facility_${key}_count`)).filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)));
      return values.length ? fmtInt(values.reduce((sum, value) => sum + Number(value), 0)) : "—";
    }, note: "学校・保育・医療・図書館・公共施設", unit: "施設" },
    { label: "1km圏の路線", value: (d) => fmtInt(metric(d, "nearby_line_count")), note: "駅中心1km圏", unit: "路線" },
    { label: "駅別乗降客数 合計", value: (d) => fmtInt(metric(d, "ridership_daily")), note: "公開駅別データの合計", unit: "人/日" },
    { label: "洪水浸水想定区域人口", value: (d) => fmt(metric(d, "hazard_flood_population_share"), 1), note: "2025推計人口の区域曝露。データ未生成時は—", unit: "%" },
    { label: "30年 震度6弱以上", value: (d) => fmt(metric(d, "seismic_30y_6lower_probability"), 1), note: "J-SHIS・人口加重。データ未生成時は—", unit: "%" },
    { label: "人口加重平均標高", value: (d) => fmt(metric(d, "terrain_elevation_population_weighted_mean"), 1), note: "250mメッシュ中心代表値", unit: "m" },
  ];

  function updateUrl(codes) {
    const url = new URL(location.href);
    if (codes.length) url.searchParams.set("codes", codes.join(","));
    else url.searchParams.delete("codes");
    history.replaceState(null, "", url);
  }

  function removeStation(code) {
    shortlist()?.remove(code);
    const codes = selectedCodes().filter((item) => String(item) !== String(code));
    updateUrl(codes);
    render().catch(console.error);
  }

  function stationHeader(detail) {
    const name = String(detail?.name || detail?.station_code || "駅");
    const shown = name.endsWith("駅") ? name : `${name}駅`;
    return `<div class="station-compare-cell station-compare-station-head">
      <strong>${escapeHtml(shown)}</strong>
      <small>${escapeHtml(detail?.primary_ward_name || "")} / 信頼度 ${escapeHtml(detail?.confidence || "—")}</small>
      <div>
        <a href="./station/${escapeHtml(detail.station_code)}/">詳細</a>
        <a href="${propertySearchUrl(name)}" target="_blank" rel="noreferrer">物件検索</a>
        <button type="button" data-remove-compare="${escapeHtml(detail.station_code)}">外す</button>
      </div>
    </div>`;
  }

  function metricCell(metricDef, detail) {
    const value = metricDef.value(detail);
    return `<div class="station-compare-cell station-compare-value"><strong>${escapeHtml(value)}${value === "—" ? "" : escapeHtml(metricDef.unit || "")}</strong><small>${escapeHtml(metricDef.note || "")}</small></div>`;
  }

  function renderGrid(details) {
    const columns = details.length;
    let html = renderDecisionSummary(details);
    html += `<div class="station-compare-scroll"><div class="station-compare-grid" style="--station-columns:${columns}">`;
    html += '<div class="station-compare-cell station-compare-label">比較項目</div>';
    html += details.map(stationHeader).join("");
    METRICS.forEach((metricDef) => {
      html += `<div class="station-compare-cell station-compare-label">${escapeHtml(metricDef.label)}</div>`;
      html += details.map((detail) => metricCell(metricDef, detail)).join("");
    });
    html += "</div></div>";
    html += '<p class="station-compare-note">数値の高低は、そのまま「住みやすい / 住みにくい」を意味しません。価格、防災、人口、交通などは希望条件によって評価が逆になります。防災値は住所・物件単位の公式ハザード情報で最終確認してください。</p>';
    return html;
  }

  function emptyState(count) {
    return `<div class="station-compare-empty"><h2>${count ? "比較には2駅必要です" : "比較する駅がまだありません"}</h2><p>駅検索やおすすめ結果から「候補に保存」を押すと、最大3駅を横並びにできます。</p><a href="./stations.html">駅を探す</a></div>`;
  }

  function bindActions(target, details) {
    target.querySelectorAll("[data-remove-compare]").forEach((button) => {
      button.addEventListener("click", () => removeStation(button.dataset.removeCompare));
    });
    target.querySelector("#station-compare-lens")?.addEventListener("change", (event) => {
      activeLens = event.target.value in LENSES ? event.target.value : "balanced";
      const current = target.querySelector(".station-compare-summary");
      if (!current) return;
      const holder = document.createElement("div");
      holder.innerHTML = renderDecisionSummary(details);
      current.replaceWith(holder.firstElementChild);
      bindActions(target, details);
    });
  }

  async function render() {
    const target = root();
    if (!target) return;
    const codes = selectedCodes();
    if (codes.length < 2) {
      target.innerHTML = emptyState(codes.length);
      return;
    }

    const results = await Promise.allSettled(codes.map((code) => loadJson(`./data/geo/station/${code}.json`)));
    const details = results.filter((result) => result.status === "fulfilled").map((result) => result.value);
    if (details.length < 2) {
      target.innerHTML = emptyState(details.length);
      return;
    }
    target.innerHTML = renderGrid(details);
    bindActions(target, details);
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!shortlist()) return;
    render().catch((error) => {
      console.warn("station compare unavailable", error);
      const target = root();
      if (target) target.innerHTML = '<div class="station-compare-empty"><h2>比較データを読み込めませんでした</h2><p>時間をおいて再読み込みしてください。</p></div>';
    });
  });
})();
