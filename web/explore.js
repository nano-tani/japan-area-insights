(() => {
  const exploreState = {
    data: null,
    stations: [],
    theme: "market",
    sortMetric: null,
    order: "desc",
    filters: [],
    compareTheme: "people",
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));
  }

  function normalize(value) {
    return String(value ?? "").trim().toLowerCase().replace(/[\s　]+/g, "");
  }

  function catalog(key) {
    return exploreState.data?.metric_catalog?.[key] || { key, label: key, unit: "", direction: "neutral" };
  }

  function metricItem(ward, key) {
    return ward?.metrics?.[key] || null;
  }

  function metricValue(ward, key) {
    const value = metricItem(ward, key)?.value;
    return value === null || value === undefined || Number.isNaN(Number(value)) ? null : Number(value);
  }

  function formatValue(key, value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const meta = catalog(key);
    const unit = meta.unit || "";
    const number = Number(value);
    if (unit === "円/㎡") return `${Math.round(number).toLocaleString("ja-JP")}円/㎡`;
    if (unit === "千円/人") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}千円/人`;
    if (["人", "件", "戸", "事業所", "施設"].includes(unit)) return `${Math.round(number).toLocaleString("ja-JP")}${unit}`;
    if (unit === "点") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}点`;
    if (unit === "%") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}%`;
    return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 2 })}${unit}`;
  }

  function relativeLabel(item, key) {
    if (!item || item.value === null || item.value === undefined) return "";
    const meta = catalog(key);
    const pct = meta.direction === "lower" ? item.percentile_low : item.percentile_high;
    if (pct === null || pct === undefined) return "";
    const edge = Math.max(1, Math.min(100, Math.ceil(Number(pct))));
    return meta.direction === "lower" ? `低い方 ${edge}%` : `高い方 ${edge}%`;
  }

  function currentTheme() {
    return exploreState.data?.themes?.find((theme) => theme.key === exploreState.theme) || exploreState.data?.themes?.[0] || null;
  }

  function themeForMetric(metricKey) {
    return exploreState.data?.themes?.find((theme) => (theme.metrics || []).includes(metricKey)) || null;
  }

  function renderThemeGrid() {
    const target = $("#theme-grid");
    if (!target || !exploreState.data) return;
    target.innerHTML = exploreState.data.themes.map((theme) => `
      <button class="theme-card ${theme.key === exploreState.theme ? "is-active" : ""}" type="button" data-theme="${escapeHtml(theme.key)}">
        <span>${escapeHtml(theme.label)}</span>
        <strong>${escapeHtml(theme.description)}</strong>
        <small>${(theme.metrics || []).map((key) => escapeHtml(catalog(key).label)).slice(0, 3).join(" / ")}</small>
      </button>
    `).join("");
    target.querySelectorAll("[data-theme]").forEach((button) => {
      button.addEventListener("click", () => {
        selectTheme(button.dataset.theme, true);
      });
    });
  }

  function populateThemeSelect() {
    const select = $("#explore-theme");
    if (!select || !exploreState.data) return;
    select.innerHTML = exploreState.data.themes.map((theme) => `<option value="${escapeHtml(theme.key)}">${escapeHtml(theme.label)}</option>`).join("");
    select.value = exploreState.theme;
  }

  function populateSortAndFilterControls() {
    const theme = currentTheme();
    if (!theme) return;
    const sort = $("#explore-sort");
    const filterMetric = $("#filter-metric");
    const options = (theme.metrics || []).map((key) => `<option value="${escapeHtml(key)}">${escapeHtml(catalog(key).label)}</option>`).join("");
    if (sort) {
      sort.innerHTML = options;
      if (!theme.metrics.includes(exploreState.sortMetric)) exploreState.sortMetric = theme.metrics[0];
      sort.value = exploreState.sortMetric;
    }
    if (filterMetric) filterMetric.innerHTML = options;
  }

  function renderFilters() {
    const target = $("#active-filters");
    if (!target) return;
    if (!exploreState.filters.length) {
      target.innerHTML = `<span class="filter-empty">追加条件なし</span>`;
      return;
    }
    target.innerHTML = exploreState.filters.map((filter, index) => `
      <button type="button" class="filter-chip" data-filter-index="${index}" title="クリックして削除">
        ${escapeHtml(catalog(filter.key).label)} ${filter.op === "gte" ? "≥" : "≤"} ${escapeHtml(formatValue(filter.key, filter.value))} ×
      </button>
    `).join("");
    target.querySelectorAll("[data-filter-index]").forEach((button) => {
      button.addEventListener("click", () => {
        exploreState.filters.splice(Number(button.dataset.filterIndex), 1);
        renderFilters();
        renderExploreTable();
      });
    });
  }

  function filteredWards() {
    const wards = [...(exploreState.data?.wards || [])];
    return wards.filter((ward) => exploreState.filters.every((filter) => {
      const value = metricValue(ward, filter.key);
      if (value === null) return false;
      return filter.op === "gte" ? value >= filter.value : value <= filter.value;
    }));
  }

  function renderExploreTable() {
    const theme = currentTheme();
    const head = $("#explore-head");
    const body = $("#explore-body");
    if (!theme || !head || !body) return;
    const keys = theme.metrics || [];
    const sortKey = exploreState.sortMetric || keys[0];
    let wards = filteredWards().filter((ward) => metricValue(ward, sortKey) !== null);
    wards.sort((a, b) => {
      const av = metricValue(a, sortKey);
      const bv = metricValue(b, sortKey);
      const delta = exploreState.order === "asc" ? av - bv : bv - av;
      return delta || a.area_id.localeCompare(b.area_id);
    });

    head.innerHTML = `<tr><th>区</th>${keys.map((key) => `<th>${escapeHtml(catalog(key).label)}</th>`).join("")}<th>信頼度</th></tr>`;
    body.innerHTML = wards.map((ward) => `
      <tr data-explore-area="${escapeHtml(ward.area_id)}" tabindex="0">
        <td><strong>${escapeHtml(ward.municipality_name)}</strong><small>詳細を見る →</small></td>
        ${keys.map((key) => {
          const item = metricItem(ward, key);
          return `<td><strong>${escapeHtml(formatValue(key, item?.value))}</strong><small>${escapeHtml(relativeLabel(item, key))}</small></td>`;
        }).join("")}
        <td><span class="quality-badge quality-${escapeHtml(ward.confidence || "D")}">${escapeHtml(ward.confidence || "—")}</span></td>
      </tr>
    `).join("");

    const empty = $("#explore-empty");
    if (empty) empty.hidden = wards.length !== 0;
    const count = $("#explore-result-count");
    if (count) count.textContent = `${wards.length}区`;
    const note = $("#explore-note");
    if (note) note.textContent = `${catalog(sortKey).label}を${exploreState.order === "asc" ? "低い" : "高い"}順に表示`;

    body.querySelectorAll("[data-explore-area]").forEach((row) => {
      const open = () => { location.href = `./ward.html?id=${encodeURIComponent(row.dataset.exploreArea)}`; };
      row.addEventListener("click", open);
      row.addEventListener("keydown", (event) => { if (event.key === "Enter") open(); });
    });
  }

  function selectTheme(themeKey, scroll = false) {
    const exists = exploreState.data?.themes?.some((theme) => theme.key === themeKey);
    if (!exists) return;
    exploreState.theme = themeKey;
    exploreState.sortMetric = currentTheme()?.metrics?.[0] || null;
    exploreState.filters = [];
    populateThemeSelect();
    populateSortAndFilterControls();
    renderThemeGrid();
    renderFilters();
    renderExploreTable();
    if (scroll) $("#discover")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function addFilter() {
    const key = $("#filter-metric")?.value;
    const op = $("#filter-operator")?.value || "gte";
    const raw = $("#filter-value")?.value;
    if (!key || raw === "" || Number.isNaN(Number(raw))) return;
    exploreState.filters.push({ key, op, value: Number(raw) });
    $("#filter-value").value = "";
    renderFilters();
    renderExploreTable();
  }

  function renderCompareTabs() {
    const target = $("#compare-tabs");
    if (!target || !exploreState.data) return;
    const allowed = ["people", "housing", "economy", "life", "urban", "resilience"];
    target.innerHTML = allowed.map((key) => {
      const theme = exploreState.data.themes.find((item) => item.key === key);
      if (!theme) return "";
      return `<button type="button" role="tab" aria-selected="${key === exploreState.compareTheme}" class="${key === exploreState.compareTheme ? "is-active" : ""}" data-compare-theme="${key}">${escapeHtml(theme.label)}</button>`;
    }).join("");
    target.querySelectorAll("[data-compare-theme]").forEach((button) => {
      button.addEventListener("click", () => {
        exploreState.compareTheme = button.dataset.compareTheme;
        renderCompareTabs();
        renderCompareDetail();
      });
    });
  }

  function ensureCompareOptions() {
    const a = $("#compare-a");
    const b = $("#compare-b");
    if (!a || !b || a.options.length) return;
    const options = (exploreState.data?.wards || []).map((ward) => `<option value="${ward.area_id}">${escapeHtml(ward.municipality_name)}</option>`).join("");
    a.innerHTML = options;
    b.innerHTML = options;
    if (b.options.length > 1) b.selectedIndex = 1;
  }

  function compareThemeCard(ward, theme) {
    if (!ward) return `<div class="data-missing">地域を選択してください。</div>`;
    return `<article class="compare-detail-card">
      <div class="compare-detail-head"><span>${escapeHtml(theme.label)}</span><h3>${escapeHtml(ward.municipality_name)}</h3></div>
      ${(theme.metrics || []).map((key) => {
        const item = metricItem(ward, key);
        return `<div class="compare-detail-row"><div><span>${escapeHtml(catalog(key).label)}</span><small>${escapeHtml(item?.period || "")}</small></div><div><strong>${escapeHtml(formatValue(key, item?.value))}</strong><small>${escapeHtml(relativeLabel(item, key))}</small></div></div>`;
      }).join("")}
    </article>`;
  }

  function renderCompareDetail() {
    if (!exploreState.data) return;
    ensureCompareOptions();
    const theme = exploreState.data.themes.find((item) => item.key === exploreState.compareTheme);
    const aId = $("#compare-a")?.value;
    const bId = $("#compare-b")?.value;
    const a = exploreState.data.wards.find((ward) => ward.area_id === aId);
    const b = exploreState.data.wards.find((ward) => ward.area_id === bId);
    const target = $("#compare-detail-grid");
    if (target && theme) target.innerHTML = compareThemeCard(a, theme) + compareThemeCard(b, theme);
  }

  function stationHref(station) {
    return `./stations.html?q=${encodeURIComponent(station.name)}`;
  }

  function searchResults(query) {
    const q = normalize(query);
    if (!q || !exploreState.data) return [];
    const results = [];

    exploreState.data.wards
      .filter((ward) => normalize(ward.municipality_name).includes(q))
      .slice(0, 5)
      .forEach((ward) => results.push({ type: "区", title: ward.municipality_name, note: "区詳細", href: `./ward.html?id=${ward.area_id}` }));

    exploreState.stations
      .filter((station) => normalize(`${station.name}${station.primary_ward_name || ""}`).includes(q))
      .slice(0, 6)
      .forEach((station) => results.push({ type: "駅", title: station.name, note: `${station.primary_ward_name || ""} / 1km圏`, href: stationHref(station) }));

    exploreState.data.themes.forEach((theme) => {
      const haystack = normalize(`${theme.label}${theme.description}${(theme.aliases || []).join("")}`);
      if (haystack.includes(q)) results.push({ type: "テーマ", title: theme.label, note: theme.description, theme: theme.key });
    });

    Object.values(exploreState.data.metric_catalog || {}).forEach((meta) => {
      const haystack = normalize(`${meta.label || ""}${meta.description || ""}`);
      if (!haystack.includes(q)) return;
      const theme = themeForMetric(meta.key);
      if (!theme) return;
      results.push({ type: "指標", title: meta.label, note: `${theme.label}で比較`, theme: theme.key, metric: meta.key });
    });

    const unique = [];
    const seen = new Set();
    for (const item of results) {
      const id = `${item.type}:${item.title}`;
      if (seen.has(id)) continue;
      seen.add(id);
      unique.push(item);
      if (unique.length >= 14) break;
    }
    return unique;
  }

  function renderGlobalSearch(query) {
    const target = $("#global-search-results");
    const input = $("#global-search");
    if (!target || !input) return;
    const results = searchResults(query);
    if (!query.trim()) {
      target.hidden = true;
      input.setAttribute("aria-expanded", "false");
      return;
    }
    target.hidden = false;
    input.setAttribute("aria-expanded", "true");
    target.innerHTML = results.length ? results.map((item, index) => `
      ${item.href
        ? `<a class="search-result-item" href="${escapeHtml(item.href)}"><span>${escapeHtml(item.type)}</span><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.note || "")}</small></div></a>`
        : `<button class="search-result-item" type="button" data-search-result="${index}"><span>${escapeHtml(item.type)}</span><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.note || "")}</small></div></button>`}
    `).join("") : `<div class="search-no-result">該当候補がありません。テーマ一覧から選べます。</div>`;
    target.querySelectorAll("[data-search-result]").forEach((button) => {
      button.addEventListener("click", () => {
        const item = results[Number(button.dataset.searchResult)];
        if (!item) return;
        selectTheme(item.theme, true);
        if (item.metric && currentTheme()?.metrics?.includes(item.metric)) {
          exploreState.sortMetric = item.metric;
          populateSortAndFilterControls();
          renderExploreTable();
        }
        target.hidden = true;
      });
    });
  }

  function bindEvents() {
    $("#explore-theme")?.addEventListener("change", (event) => selectTheme(event.target.value));
    $("#explore-sort")?.addEventListener("change", (event) => {
      exploreState.sortMetric = event.target.value;
      renderExploreTable();
    });
    $("#explore-order")?.addEventListener("change", (event) => {
      exploreState.order = event.target.value;
      renderExploreTable();
    });
    $("#filter-add")?.addEventListener("click", addFilter);
    $("#filter-value")?.addEventListener("keydown", (event) => { if (event.key === "Enter") addFilter(); });
    $("#compare-a")?.addEventListener("change", renderCompareDetail);
    $("#compare-b")?.addEventListener("change", renderCompareDetail);
    $("#global-search")?.addEventListener("input", (event) => renderGlobalSearch(event.target.value));
    $("#global-search")?.addEventListener("keydown", (event) => {
      if (event.key === "Escape") $("#global-search-results").hidden = true;
    });
    $$('[data-search-example]').forEach((button) => {
      button.addEventListener("click", () => {
        const input = $("#global-search");
        input.value = button.dataset.searchExample;
        input.focus();
        renderGlobalSearch(input.value);
      });
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".global-search-wrap")) {
        const target = $("#global-search-results");
        if (target) target.hidden = true;
      }
    });
  }

  function fallbackFromCore(areas) {
    const catalog = {
      "core.total_score": { key: "core.total_score", label: "総合評価", unit: "点", direction: "higher", kind: "core" },
      "core.price_score": { key: "core.price_score", label: "価格動向", unit: "点", direction: "higher", kind: "core" },
      "core.population_score": { key: "core.population_score", label: "人口動向", unit: "点", direction: "higher", kind: "core" },
      "core.future_population_score": { key: "core.future_population_score", label: "将来人口", unit: "点", direction: "higher", kind: "core" },
      "core.convenience_score": { key: "core.convenience_score", label: "生活利便性", unit: "点", direction: "higher", kind: "core" },
      "core.transport_score": { key: "core.transport_score", label: "交通利便性", unit: "点", direction: "higher", kind: "core" },
      "core.transaction_score": { key: "core.transaction_score", label: "取引活性度", unit: "点", direction: "higher", kind: "core" },
    };
    return {
      generated_at: null,
      peer_group: "tokyo23:ward",
      themes: [
        { key: "market", label: "価格・不動産", description: "価格動向から探す", metrics: ["core.price_score"], aliases: ["地価", "価格", "不動産"] },
        { key: "people", label: "人口・将来", description: "人口と将来性から探す", metrics: ["core.population_score", "core.future_population_score"], aliases: ["人口", "将来人口"] },
        { key: "life", label: "生活・子育て", description: "生活利便性から探す", metrics: ["core.convenience_score"], aliases: ["生活", "子育て"] },
        { key: "mobility", label: "交通・移動", description: "交通利便性から探す", metrics: ["core.transport_score"], aliases: ["交通", "駅"] },
      ],
      metric_catalog: catalog,
      wards: areas.map((area) => ({
        area_id: area.area_id,
        prefecture_name: area.prefecture_name,
        municipality_name: area.municipality_name,
        confidence: area.confidence,
        metrics: Object.fromEntries(Object.entries({
          "core.total_score": area.total_score,
          "core.price_score": area.price_score,
          "core.population_score": area.population_score,
          "core.future_population_score": area.future_population_score,
          "core.convenience_score": area.convenience_score,
          "core.transport_score": area.transport_score,
          "core.transaction_score": area.transaction_score,
        }).map(([key, value]) => [key, { value, period: area.calculation_date, quality: area.confidence }]))
      })),
      fallback: true,
    };
  }

  async function init() {
    try {
      const [exploreResult, stationResult] = await Promise.allSettled([
        loadJson("./data/explore/wards.json"),
        loadJson("./data/geo/index.json"),
      ]);
      if (exploreResult.status === "fulfilled") {
        exploreState.data = exploreResult.value;
      } else {
        exploreState.data = fallbackFromCore(await loadJson("./data/areas.json"));
      }
      exploreState.stations = stationResult.status === "fulfilled" ? (stationResult.value.station_areas || []) : [];
      exploreState.theme = exploreState.data.themes?.[0]?.key || "market";
      exploreState.sortMetric = exploreState.data.themes?.[0]?.metrics?.[0] || null;
      populateThemeSelect();
      populateSortAndFilterControls();
      renderThemeGrid();
      renderFilters();
      renderExploreTable();
      renderCompareTabs();
      renderCompareDetail();
      bindEvents();
      if (exploreState.data.fallback) {
        const note = $("#explore-note");
        if (note) note.textContent = "詳細分析インデックスは次回データ更新後に有効になります。現在は基本スコアで検索できます。";
      }
    } catch (error) {
      console.error("discovery UI unavailable", error);
      const body = $("#explore-body");
      if (body) body.innerHTML = `<tr><td colspan="6"><div class="data-missing">探索データを読み込めませんでした。</div></td></tr>`;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
