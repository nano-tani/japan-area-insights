(() => {
  const AXES = [
    {
      key: "affordability",
      label: "価格の手頃さ",
      description: "地価・取引単価が低い地域を優先",
      defaultWeight: 2,
      metrics: [
        ["market.land_price_median", "lower"],
        ["market.median_unit_price", "lower"],
      ],
    },
    {
      key: "market",
      label: "市場の活発さ",
      description: "価格動向と取引の活発さを重視",
      defaultWeight: 2,
      metrics: [
        ["core.price_score", "higher"],
        ["core.transaction_score", "higher"],
      ],
    },
    {
      key: "population",
      label: "人口の勢い",
      description: "現在の人口動向と自然増減を重視",
      defaultWeight: 3,
      metrics: [
        ["core.population_score", "higher"],
        ["demographics.natural_change", "higher"],
      ],
    },
    {
      key: "future",
      label: "将来人口",
      description: "2045年まで人口を維持しやすい地域を優先",
      defaultWeight: 3,
      metrics: [
        ["core.future_population_score", "higher"],
        ["people.retention_2045", "higher"],
      ],
    },
    {
      key: "housing",
      label: "住宅の新しさ",
      description: "新しい住宅が多く、築古住宅が少ない地域を優先",
      defaultWeight: 2,
      metrics: [
        ["housing2023.post2011_share", "higher"],
        ["housing2023.pre1980_share", "lower"],
      ],
    },
    {
      key: "economy",
      label: "仕事・経済の集積",
      description: "所得・昼間人口・雇用の集積を重視",
      defaultWeight: 2,
      metrics: [
        ["economy.taxable_income_per_taxpayer", "higher"],
        ["economy.day_night_population_ratio", "higher"],
        ["economy.employees", "higher"],
        ["economy.establishments", "higher"],
      ],
    },
    {
      key: "life",
      label: "生活利便性",
      description: "学校・保育・医療・図書館などの利便性を重視",
      defaultWeight: 3,
      metrics: [
        ["core.convenience_score", "higher"],
      ],
    },
    {
      key: "transport",
      label: "交通利便性",
      description: "駅・路線・乗降客数から交通の強さを重視",
      defaultWeight: 3,
      metrics: [
        ["core.transport_score", "higher"],
      ],
    },
    {
      key: "urban",
      label: "都市の集積",
      description: "人口集中地区や高い容積率など都市型の街を優先",
      defaultWeight: 1,
      metrics: [
        ["urban.did_mesh_share", "higher"],
        ["market.transaction_far_median", "higher"],
      ],
    },
    {
      key: "resilience",
      label: "防災",
      description: "洪水・液状化・高潮・土砂災害の人口曝露が低い地域を優先",
      defaultWeight: 3,
      metrics: [
        ["hazard.flood_population_share", "lower"],
        ["hazard.liquefaction_population_share", "lower"],
        ["hazard.storm_surge_population_share", "lower"],
        ["hazard.sediment_population_share", "lower"],
      ],
    },
  ];

  const PRESETS = {
    balanced: { label: "バランス", weights: { affordability: 2, market: 2, population: 3, future: 3, housing: 2, economy: 2, life: 3, transport: 3, urban: 1, resilience: 3 } },
    future: { label: "将来性", weights: { affordability: 1, market: 2, population: 5, future: 5, housing: 2, economy: 3, life: 2, transport: 3, urban: 1, resilience: 3 } },
    daily: { label: "暮らし・交通", weights: { affordability: 3, market: 0, population: 2, future: 2, housing: 3, economy: 1, life: 5, transport: 5, urban: 1, resilience: 4 } },
    safety: { label: "防災重視", weights: { affordability: 2, market: 0, population: 1, future: 2, housing: 2, economy: 0, life: 2, transport: 2, urban: 0, resilience: 5 } },
    affordable: { label: "手頃さ", weights: { affordability: 5, market: 0, population: 2, future: 2, housing: 2, economy: 0, life: 3, transport: 3, urban: 0, resilience: 3 } },
    urban: { label: "都心・利便", weights: { affordability: 0, market: 3, population: 2, future: 2, housing: 1, economy: 5, life: 4, transport: 5, urban: 5, resilience: 1 } },
  };

  const state = {
    data: null,
    axes: [],
    weights: {},
    utilities: new Map(),
    activePreset: "balanced",
  };

  const $ = (selector) => document.querySelector(selector);

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '\"': "&quot;",
    }[char]));
  }

  function numeric(value) {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function metricValue(ward, key) {
    return numeric(ward?.metrics?.[key]?.value);
  }

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function fallbackData(areas) {
    const metricKeys = [
      "core.total_score", "core.price_score", "core.population_score",
      "core.future_population_score", "core.convenience_score",
      "core.transport_score", "core.transaction_score",
    ];
    return {
      fallback: true,
      wards: areas.map((area) => ({
        area_id: String(area.area_id),
        municipality_name: area.municipality_name,
        confidence: area.confidence,
        metrics: Object.fromEntries(metricKeys.map((key) => {
          const column = key.replace("core.", "");
          return [key, { value: area[column] ?? null }];
        })),
      })),
    };
  }

  function averageTieRankUtilities(rows, orientation) {
    const sorted = [...rows].sort((a, b) => a.value - b.value || a.areaId.localeCompare(b.areaId));
    const result = new Map();
    const n = sorted.length;
    if (!n) return result;
    if (n === 1) {
      result.set(sorted[0].areaId, 50);
      return result;
    }

    let i = 0;
    while (i < n) {
      let j = i + 1;
      while (j < n && sorted[j].value === sorted[i].value) j += 1;
      const averageIndex = (i + (j - 1)) / 2;
      const higherScore = averageIndex / (n - 1) * 100;
      const utility = orientation === "lower" ? 100 - higherScore : higherScore;
      for (let k = i; k < j; k += 1) result.set(sorted[k].areaId, utility);
      i = j;
    }
    return result;
  }

  function buildUtilities() {
    state.utilities = new Map();
    const wards = state.data?.wards || [];
    const metricPairs = AXES.flatMap((axis) => axis.metrics.map(([key, orientation]) => [key, orientation]));
    const seen = new Set();

    metricPairs.forEach(([key, orientation]) => {
      const id = `${key}:${orientation}`;
      if (seen.has(id)) return;
      seen.add(id);
      const rows = wards
        .map((ward) => ({ areaId: String(ward.area_id), value: metricValue(ward, key) }))
        .filter((row) => row.value !== null);
      if (rows.length < 3) return;
      state.utilities.set(id, averageTieRankUtilities(rows, orientation));
    });

    state.axes = AXES.map((axis) => {
      const availableMetrics = axis.metrics.filter(([key, orientation]) => state.utilities.has(`${key}:${orientation}`));
      return { ...axis, availableMetrics, enabled: availableMetrics.length > 0 };
    });
  }

  function importanceLabel(value) {
    return ["重視しない", "少し", "やや重視", "重視", "かなり重視", "最重要"][Number(value)] || "重視しない";
  }

  function axisScore(ward, axis) {
    const values = axis.availableMetrics
      .map(([key, orientation]) => state.utilities.get(`${key}:${orientation}`)?.get(String(ward.area_id)))
      .filter((value) => value !== null && value !== undefined);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function selectedWeightTotal() {
    return state.axes.reduce((sum, axis) => sum + (axis.enabled ? Number(state.weights[axis.key] || 0) : 0), 0);
  }

  function scoreWard(ward) {
    const totalWeight = selectedWeightTotal();
    if (!totalWeight) return null;
    let weighted = 0;
    let coveredWeight = 0;
    const axes = [];

    state.axes.forEach((axis) => {
      if (!axis.enabled) return;
      const weight = Number(state.weights[axis.key] || 0);
      if (!weight) return;
      const value = axisScore(ward, axis);
      if (value === null) {
        axes.push({ key: axis.key, label: axis.label, weight, score: null, contribution: 0 });
        return;
      }
      weighted += value * weight;
      coveredWeight += weight;
      axes.push({ key: axis.key, label: axis.label, weight, score: value, contribution: value * weight });
    });

    return {
      ward,
      score: weighted / totalWeight,
      coverage: coveredWeight / totalWeight * 100,
      axes,
    };
  }

  function bestReasons(result) {
    return result.axes
      .filter((axis) => axis.score !== null && axis.weight > 0)
      .sort((a, b) => b.contribution - a.contribution || b.score - a.score)
      .slice(0, 3);
  }

  function weakestReason(result) {
    return result.axes
      .filter((axis) => axis.score !== null && axis.weight >= 3)
      .sort((a, b) => a.score - b.score)[0] || null;
  }

  function renderResults() {
    const target = $("#recommend-results");
    const status = $("#recommend-status");
    if (!target) return;

    const totalWeight = selectedWeightTotal();
    if (!totalWeight) {
      target.innerHTML = `<div class="recommend-empty">少なくとも1項目を「少し」以上にすると、おすすめ地域を計算します。</div>`;
      if (status) status.textContent = "重視する項目を選んでください";
      return;
    }

    const results = (state.data?.wards || [])
      .map(scoreWard)
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || b.coverage - a.coverage || String(a.ward.area_id).localeCompare(String(b.ward.area_id)))
      .slice(0, 6);

    if (!results.length) {
      target.innerHTML = `<div class="recommend-empty">計算できる地域がありません。重視項目を変更してください。</div>`;
      return;
    }

    target.innerHTML = results.map((result, index) => {
      const reasons = bestReasons(result);
      const weak = weakestReason(result);
      const confidence = result.ward.confidence || "—";
      return `<a class="recommend-card" data-rank="${index + 1}" href="./ward.html?id=${encodeURIComponent(result.ward.area_id)}">
        <span class="recommend-card-rank">#${index + 1} MATCH</span>
        <div class="recommend-card-top">
          <h4>${escapeHtml(result.ward.municipality_name)}</h4>
          <div class="recommend-match"><strong>${Math.round(result.score)}</strong><span>一致度 / 100</span></div>
        </div>
        <div class="recommend-reasons">
          ${reasons.map((reason) => `<span class="recommend-reason">${escapeHtml(reason.label)} ${Math.round(reason.score)}</span>`).join("")}
        </div>
        ${weak && weak.score < 45 ? `<div class="recommend-weak">注意: ${escapeHtml(weak.label)}は相対的に弱め（${Math.round(weak.score)}）</div>` : ""}
        <div class="recommend-card-foot"><span>データ反映 ${Math.round(result.coverage)}%</span><span>信頼度 ${escapeHtml(confidence)} →</span></div>
      </a>`;
    }).join("");

    if (status) {
      const enabledCount = state.axes.filter((axis) => axis.enabled && Number(state.weights[axis.key] || 0) > 0).length;
      status.textContent = `${enabledCount}項目の好みから計算`;
    }
  }

  function sliderHtml(axis) {
    const value = axis.enabled ? Number(state.weights[axis.key] || 0) : 0;
    const unavailable = axis.metrics.length - axis.availableMetrics.length;
    const availability = axis.enabled
      ? (unavailable > 0 ? `${axis.availableMetrics.length}/${axis.metrics.length}指標で計算` : `${axis.metrics.length}指標で計算`)
      : "詳細データ更新後に利用可能";
    return `<div class="recommend-slider${axis.enabled ? "" : " is-disabled"}">
      <div class="recommend-slider-head">
        <strong>${escapeHtml(axis.label)}</strong>
        <output id="recommend-output-${escapeHtml(axis.key)}">${escapeHtml(importanceLabel(value))}</output>
      </div>
      <p>${escapeHtml(axis.description)}</p>
      <input type="range" min="0" max="5" step="1" value="${value}" data-recommend-axis="${escapeHtml(axis.key)}" ${axis.enabled ? "" : "disabled"} aria-label="${escapeHtml(axis.label)}の重要度">
      <div class="recommend-scale"><span>重視しない</span><span>最重要</span></div>
      <span class="recommend-unavailable">${escapeHtml(availability)}</span>
    </div>`;
  }

  function renderSliders() {
    const target = $("#recommend-sliders");
    if (!target) return;
    target.innerHTML = state.axes.map(sliderHtml).join("");
    target.querySelectorAll("[data-recommend-axis]").forEach((input) => {
      input.addEventListener("input", () => {
        state.weights[input.dataset.recommendAxis] = Number(input.value);
        state.activePreset = null;
        const output = $(`#recommend-output-${input.dataset.recommendAxis}`);
        if (output) output.textContent = importanceLabel(input.value);
        renderPresetState();
        renderResults();
      });
    });
  }

  function renderPresetState() {
    document.querySelectorAll("[data-recommend-preset]").forEach((button) => {
      button.classList.toggle("is-active", Boolean(state.activePreset) && button.dataset.recommendPreset === state.activePreset);
    });
  }

  function applyPreset(key) {
    const preset = PRESETS[key];
    if (!preset) return;
    state.activePreset = key;
    state.axes.forEach((axis) => {
      state.weights[axis.key] = axis.enabled ? Number(preset.weights[axis.key] ?? axis.defaultWeight ?? 0) : 0;
    });
    renderSliders();
    renderPresetState();
    renderResults();
  }

  function clearWeights() {
    state.activePreset = null;
    state.axes.forEach((axis) => { state.weights[axis.key] = 0; });
    renderSliders();
    renderPresetState();
    renderResults();
  }

  function renderPresets() {
    const target = $("#recommend-presets");
    if (!target) return;
    target.innerHTML = Object.entries(PRESETS).map(([key, preset]) => `<button type="button" data-recommend-preset="${escapeHtml(key)}">${escapeHtml(preset.label)}</button>`).join("");
    target.querySelectorAll("[data-recommend-preset]").forEach((button) => {
      button.addEventListener("click", () => applyPreset(button.dataset.recommendPreset));
    });
    renderPresetState();
  }

  function initializeWeights() {
    state.axes.forEach((axis) => {
      state.weights[axis.key] = axis.enabled ? Number(PRESETS.balanced.weights[axis.key] ?? axis.defaultWeight ?? 0) : 0;
    });
  }

  async function init() {
    const sliders = $("#recommend-sliders");
    if (!sliders) return;
    try {
      try {
        state.data = await loadJson("./data/explore/wards.json");
      } catch (error) {
        state.data = fallbackData(await loadJson("./data/areas.json"));
      }
      buildUtilities();
      initializeWeights();
      renderPresets();
      renderSliders();
      renderResults();
      $("#recommend-clear")?.addEventListener("click", clearWeights);
      const dataNote = $("#recommend-data-note");
      if (dataNote && state.data.fallback) {
        dataNote.textContent = "現在は基本スコアで計算できる項目だけ有効です。詳細分析データ更新後に、手頃さ・住宅・経済・防災などのスライダーも自動で有効になります。";
      }
    } catch (error) {
      sliders.innerHTML = `<div class="recommend-empty">おすすめ検索データを読み込めませんでした。</div>`;
      console.error("recommendation search unavailable", error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
