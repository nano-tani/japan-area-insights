(() => {
  const AXES = [
    { key: "price", label: "価格動向", metric: "price_score", max: 20, description: "駅コード指定の取引単価の中期変化を重視", defaultWeight: 2 },
    { key: "population", label: "人口の勢い", metric: "population_score", max: 20, description: "1km圏の2020年人口→2025年推計人口を重視", defaultWeight: 2 },
    { key: "future", label: "将来人口", metric: "future_population_score", max: 20, description: "1km圏の2045年 / 2025年人口維持を重視", defaultWeight: 3 },
    { key: "convenience", label: "生活利便性", metric: "convenience_score", max: 15, description: "学校・保育・医療・図書館・公共施設を重視", defaultWeight: 3 },
    { key: "transport", label: "交通利便性", metric: "transport_score", max: 15, description: "周辺駅・路線・乗降客数を重視", defaultWeight: 4 },
    { key: "transaction", label: "取引活性度", metric: "transaction_score", max: 10, description: "駅コード指定の直近5完了年の取引件数を重視", defaultWeight: 1 },
  ];

  const PRESETS = {
    balanced: { label: "バランス", weights: { price: 2, population: 2, future: 3, convenience: 3, transport: 4, transaction: 1 } },
    future: { label: "将来性", weights: { price: 1, population: 4, future: 5, convenience: 2, transport: 2, transaction: 1 } },
    daily: { label: "生活・交通", weights: { price: 1, population: 1, future: 2, convenience: 5, transport: 5, transaction: 0 } },
    mobility: { label: "交通最優先", weights: { price: 0, population: 1, future: 1, convenience: 2, transport: 5, transaction: 0 } },
    market: { label: "市場の動き", weights: { price: 5, population: 1, future: 1, convenience: 0, transport: 2, transaction: 4 } },
  };

  const state = { stations: [], weights: {}, activePreset: "balanced" };
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function importanceLabel(value) {
    return ["重視しない", "少し", "やや", "重視", "かなり", "最重要"][Number(value) || 0];
  }

  function axisScore(station, axis) {
    const value = station?.[axis.metric];
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
    return Math.max(0, Math.min(100, Number(value) / axis.max * 100));
  }

  function selectedWeightTotal() {
    return AXES.reduce((sum, axis) => sum + Number(state.weights[axis.key] || 0), 0);
  }

  function scoreStation(station) {
    const totalWeight = selectedWeightTotal();
    if (!totalWeight) return null;
    let weighted = 0;
    let covered = 0;
    const axes = [];
    AXES.forEach((axis) => {
      const weight = Number(state.weights[axis.key] || 0);
      if (!weight) return;
      const score = axisScore(station, axis);
      axes.push({ ...axis, weight, score, contribution: score === null ? 0 : score * weight });
      if (score !== null) {
        weighted += score * weight;
        covered += weight;
      }
    });
    return {
      station,
      score: weighted / totalWeight,
      coverage: covered / totalWeight * 100,
      axes,
    };
  }

  function bestReasons(result) {
    return result.axes
      .filter((axis) => axis.score !== null)
      .sort((a, b) => b.contribution - a.contribution || b.score - a.score)
      .slice(0, 3);
  }

  function weakestReason(result) {
    return result.axes
      .filter((axis) => axis.score !== null && axis.weight >= 3)
      .sort((a, b) => a.score - b.score)[0] || null;
  }

  function renderPresets() {
    const target = $("#station-recommend-presets");
    if (!target) return;
    target.innerHTML = Object.entries(PRESETS).map(([key, preset]) => `
      <button type="button" data-station-preset="${key}" class="${state.activePreset === key ? "is-active" : ""}">${escapeHtml(preset.label)}</button>
    `).join("");
    target.querySelectorAll("[data-station-preset]").forEach((button) => {
      button.addEventListener("click", () => applyPreset(button.dataset.stationPreset));
    });
  }

  function renderSliders() {
    const target = $("#station-recommend-sliders");
    if (!target) return;
    target.innerHTML = AXES.map((axis) => {
      const value = Number(state.weights[axis.key] || 0);
      return `<div class="station-recommend-slider">
        <div class="station-recommend-slider-head"><strong>${escapeHtml(axis.label)}</strong><output id="station-output-${axis.key}">${escapeHtml(importanceLabel(value))}</output></div>
        <p>${escapeHtml(axis.description)}</p>
        <input type="range" min="0" max="5" step="1" value="${value}" data-station-axis="${axis.key}" aria-label="${escapeHtml(axis.label)}の重要度">
        <div class="station-recommend-scale"><span>重視しない</span><span>最重要</span></div>
      </div>`;
    }).join("");
    target.querySelectorAll("[data-station-axis]").forEach((input) => {
      input.addEventListener("input", () => {
        state.weights[input.dataset.stationAxis] = Number(input.value);
        state.activePreset = null;
        const output = $(`#station-output-${input.dataset.stationAxis}`);
        if (output) output.textContent = importanceLabel(input.value);
        renderPresets();
        renderResults();
      });
    });
  }

  function openStation(code) {
    if (typeof window.openStationDetail === "function") {
      window.openStationDetail(code);
      return;
    }
    const row = document.querySelector(`#station-ranking-body [data-station-code="${CSS.escape(code)}"]`);
    row?.click();
  }

  function renderResults() {
    const target = $("#station-recommend-results");
    const status = $("#station-recommend-status");
    if (!target) return;
    if (!selectedWeightTotal()) {
      target.innerHTML = `<div class="station-recommend-empty">少なくとも1項目を「少し」以上にしてください。</div>`;
      if (status) status.textContent = "重視する項目を選んでください";
      return;
    }

    const results = state.stations
      .filter((station) => station.eligibility === "eligible" && station.total_score !== null && station.total_score !== undefined)
      .map(scoreStation)
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || b.coverage - a.coverage || String(a.station.station_code).localeCompare(String(b.station.station_code)))
      .slice(0, 8);

    target.innerHTML = results.length ? results.map((result, index) => {
      const station = result.station;
      const reasons = bestReasons(result);
      const weak = weakestReason(result);
      return `<article class="station-recommend-card" data-rank="${index + 1}">
        <div class="station-recommend-card-top">
          <div><span class="station-recommend-rank">#${index + 1} MATCH</span><h3>${escapeHtml(station.name)}</h3><small>${escapeHtml(station.primary_ward_name || "")} / 駅中心1km圏</small></div>
          <div class="station-recommend-match"><strong>${Math.round(result.score)}</strong><span>一致度 / 100</span></div>
        </div>
        <span class="station-recommend-reasons-label">合っている理由</span>
        <div class="station-recommend-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason.label)} ${Math.round(reason.score)}</span>`).join("")}</div>
        ${weak && weak.score < 45 ? `<div class="station-recommend-caution"><strong>確認しておきたい点</strong><span>${escapeHtml(weak.label)}は相対的に弱め（${Math.round(weak.score)}）</span></div>` : ""}
        <div class="station-recommend-foot"><span>データ反映 ${Math.round(result.coverage)}%</span><span>信頼度 ${escapeHtml(station.confidence || "—")}</span></div>
        <button type="button" data-open-station="${escapeHtml(station.station_code)}">この駅周辺を詳しく見る</button>
      </article>`;
    }).join("") : `<div class="station-recommend-empty">条件に合う評価対象駅がありません。</div>`;

    target.querySelectorAll("[data-open-station]").forEach((button) => {
      button.addEventListener("click", () => openStation(button.dataset.openStation));
    });
    if (status) status.textContent = `${results.length}駅を表示 / 総合点算出対象駅から検索`;
  }

  function applyPreset(key) {
    const preset = PRESETS[key];
    if (!preset) return;
    state.activePreset = key;
    AXES.forEach((axis) => { state.weights[axis.key] = Number(preset.weights[axis.key] ?? 0); });
    renderPresets();
    renderSliders();
    renderResults();
  }

  function insertSection() {
    if ($("#station-recommend")) return;
    const insight = document.querySelector(".insight-strip");
    if (!insight) return;
    insight.insertAdjacentHTML("beforebegin", `
      <section id="station-recommend" class="section station-recommend-section" aria-labelledby="station-recommend-title">
        <div class="section-heading">
          <div><p class="section-kicker">FIND YOUR STATION</p><h2 id="station-recommend-title">何を重視して駅を選ぶ？</h2></div>
          <p class="section-note">0〜5で重要度を設定すると、総合点算出条件を満たす駅1km圏からあなた向けの候補を探します。</p>
        </div>
        <div class="station-recommend-shell">
          <div class="station-recommend-intro"><strong>迷ったらプリセットから</strong><span>あとから自由に調整できます</span></div>
          <div id="station-recommend-presets" class="station-recommend-presets"></div>
          <div id="station-recommend-sliders" class="station-recommend-sliders"></div>
          <div class="station-recommend-heading"><div><span>YOUR MATCHES</span><h3>あなた向けの駅</h3></div><p id="station-recommend-status">計算中</p></div>
          <div id="station-recommend-results" class="station-recommend-results" aria-live="polite"></div>
          <p class="station-recommend-note">一致度は駅エリアのCore Scoreそのものではありません。6つの駅スコアを各項目0〜100へ正規化し、あなたが指定した重要度で再加重します。人口動向は2020年人口→2025年推計人口の暫定指標です。価格・取引は駅コード指定データで、1km圏内の物件所在地を意味しません。</p>
        </div>
      </section>`);
  }

  function addCss() {
    if (document.querySelector('link[data-station-recommend-css]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "./station-recommend.css";
    link.dataset.stationRecommendCss = "true";
    document.head.appendChild(link);
  }

  async function init() {
    addCss();
    insertSection();
    const payload = await loadJson("./data/geo/index.json");
    state.stations = payload.station_areas || [];
    applyPreset("balanced");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => init().catch(console.error), { once: true });
  else init().catch(console.error);
})();