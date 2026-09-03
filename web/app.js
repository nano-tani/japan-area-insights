const state = { areas: [], meta: null, rankingMetric: "total_score" };

const $ = (selector) => document.querySelector(selector);
const score = (value) => value === null || value === undefined ? "—" : Number(value).toFixed(Number(value) % 1 ? 1 : 0);
const confidence = (value) => value || "—";
const metricLabels = {
  total_score: "総合",
  price_score: "価格動向",
  population_score: "人口動向",
  future_population_score: "将来人口",
  convenience_score: "生活利便性",
  transport_score: "交通利便性",
  transaction_score: "取引活性度",
};
const facilityLabels = {
  school: "学校",
  childcare: "保育園・幼稚園等",
  medical: "医療機関",
  library: "図書館",
  public_facility: "公共施設",
};

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

function chooseInitialRankingMetric() {
  const candidates = [
    "total_score", "price_score", "population_score", "future_population_score",
    "convenience_score", "transport_score", "transaction_score"
  ];
  return candidates.find((key) => state.areas.some((area) => area[key] !== null && area[key] !== undefined)) || "total_score";
}

function renderRanking(filter = "") {
  const body = $("#ranking-body");
  const empty = $("#empty-ranking");
  const query = filter.trim().toLowerCase();
  const metric = state.rankingMetric;
  const ranked = state.areas
    .filter((area) => area[metric] !== null && area[metric] !== undefined)
    .filter((area) => area.municipality_name.toLowerCase().includes(query))
    .sort((a, b) => Number(b[metric]) - Number(a[metric]) || a.area_id.localeCompare(b.area_id));

  $("#ranking-score-label").textContent = metricLabels[metric] || "評価";
  body.innerHTML = ranked.map((area, index) => `
    <tr data-area-id="${area.area_id}">
      <td>${index + 1}</td>
      <td><strong>${area.municipality_name}</strong></td>
      <td><span class="score-pill">${score(area[metric])}</span></td>
      <td>${score(area.price_score)}</td>
      <td>${score(area.population_score)}</td>
      <td>${score(area.future_population_score)}</td>
      <td>${score(area.convenience_score)}</td>
      <td>${score(area.transport_score)}</td>
      <td>${confidence(area.confidence)}</td>
    </tr>
  `).join("");

  empty.hidden = ranked.length !== 0;
  body.querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => openDetail(row.dataset.areaId)));
}

function setupRanking() {
  state.rankingMetric = chooseInitialRankingMetric();
  $("#ranking-metric").value = state.rankingMetric;
  $("#ranking-metric").addEventListener("change", (event) => {
    state.rankingMetric = event.target.value;
    renderRanking($("#search").value);
  });
  renderRanking();
}

function renderAreaGrid(filter = "") {
  const query = filter.trim().toLowerCase();
  const rows = state.areas.filter((area) => area.municipality_name.toLowerCase().includes(query));
  $("#area-grid").innerHTML = rows.map((area) => `
    <article class="area-card" data-area-id="${area.area_id}" tabindex="0" role="button">
      <span class="pref">${area.prefecture_name}</span>
      <h3>${area.municipality_name}</h3>
      <div class="card-foot"><span>総合 ${score(area.total_score)}</span><span>信頼度 ${confidence(area.confidence)}</span></div>
    </article>
  `).join("");

  $("#area-grid").querySelectorAll(".area-card").forEach((card) => {
    const open = () => openDetail(card.dataset.areaId);
    card.addEventListener("click", open);
    card.addEventListener("keydown", (event) => { if (event.key === "Enter") open(); });
  });
}

function setupCompare() {
  const options = state.areas.map((area) => `<option value="${area.area_id}">${area.municipality_name}</option>`).join("");
  $("#compare-a").innerHTML = options;
  $("#compare-b").innerHTML = options;
  if (state.areas.length > 1) $("#compare-b").selectedIndex = 1;
  $("#compare-a").addEventListener("change", renderCompare);
  $("#compare-b").addEventListener("change", renderCompare);
  renderCompare();
}

function compareCard(area) {
  const metrics = [
    ["総合", area.total_score], ["価格動向", area.price_score], ["人口動向", area.population_score],
    ["将来人口", area.future_population_score], ["生活利便性", area.convenience_score],
    ["交通利便性", area.transport_score], ["取引活性度", area.transaction_score], ["データ信頼度", area.confidence]
  ];
  return `<article class="compare-card">
    <h3>${area.municipality_name}</h3>
    ${metrics.map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${label === "データ信頼度" ? confidence(value) : score(value)}</strong></div>`).join("")}
  </article>`;
}

function renderCompare() {
  const a = state.areas.find((area) => area.area_id === $("#compare-a").value);
  const b = state.areas.find((area) => area.area_id === $("#compare-b").value);
  if (!a || !b) return;
  $("#compare-grid").innerHTML = compareCard(a) + compareCard(b);
}

function rowsOrMissing(rows, columns) {
  if (!rows || rows.length === 0) return `<div class="data-missing">データ未生成</div>`;
  const recent = rows.slice(-6).reverse();
  return recent.map((row) => `<div class="metric-row">${columns.map(([label, key, suffix = ""]) => `<span>${label}: <strong>${row[key] ?? "—"}${row[key] === null || row[key] === undefined ? "" : suffix}</strong></span>`).join("")}</div>`).join("");
}

function facilitySummary(rows) {
  if (!rows || rows.length === 0) return `<div class="data-missing">データ未生成</div>`;
  const byType = Object.fromEntries(rows.map((row) => [row.facility_type, row.count]));
  return Object.entries(facilityLabels).map(([key, label]) => `
    <div class="metric-row"><span>${label}</span><strong>${byType[key] ?? 0}施設</strong></div>
  `).join("");
}

function transportSummary(summary) {
  if (!summary || summary.station_count === undefined) return `<div class="data-missing">データ未生成</div>`;
  const passenger = summary.passenger_count === null || summary.passenger_count === undefined
    ? "—"
    : `${Number(summary.passenger_count).toLocaleString("ja-JP")}人/日`;
  return `
    <div class="metric-row"><span>駅数</span><strong>${summary.station_count}駅</strong></div>
    <div class="metric-row"><span>路線数</span><strong>${summary.line_count}路線</strong></div>
    <div class="metric-row"><span>駅別乗降客数 合計</span><strong>${passenger}</strong></div>
    <div class="metric-row"><span>乗降客数の基準年</span><strong>${summary.passenger_year ?? "—"}年</strong></div>
  `;
}

async function openDetail(areaId) {
  const dialog = $("#detail-dialog");
  const basic = state.areas.find((area) => area.area_id === areaId);
  $("#detail-content").innerHTML = `<div class="detail-body"><p>読み込み中...</p></div>`;
  dialog.showModal();

  try {
    const detail = await loadJson(`./data/area/${areaId}.json`);
    const totalDisplay = detail.total_score === null || detail.total_score === undefined
      ? `<div class="data-missing">総合スコアに必要なデータが不足しています。</div>`
      : `<div class="detail-score"><strong>${score(detail.total_score)}</strong><span>/ 100</span></div>`;
    $("#detail-content").innerHTML = `
      <div class="detail-body">
        <p class="section-kicker">AREA ${detail.area_id}</p>
        <h3>${detail.municipality_name}</h3>
        <p class="detail-sub">${detail.prefecture_name} / 対象地域内での相対評価</p>
        ${totalDisplay}
        <div class="metric-row"><span>価格動向</span><strong>${score(detail.price_score)} / 20</strong></div>
        <div class="metric-row"><span>人口動向</span><strong>${score(detail.population_score)} / 20</strong></div>
        <div class="metric-row"><span>将来人口</span><strong>${score(detail.future_population_score)} / 20</strong></div>
        <div class="metric-row"><span>生活利便性</span><strong>${score(detail.convenience_score)} / 15</strong></div>
        <div class="metric-row"><span>交通利便性</span><strong>${score(detail.transport_score)} / 15</strong></div>
        <div class="metric-row"><span>取引活性度</span><strong>${score(detail.transaction_score)} / 10</strong></div>
        <div class="metric-row"><span>データ信頼度</span><strong>${confidence(detail.confidence)}</strong></div>
        <section class="detail-section"><h4>地価推移</h4>${rowsOrMissing(detail.prices, [["年", "year"], ["公示地価", "official_land_price", "円/㎡"], ["前年比", "yoy_change", "%"], ["5年変化", "change_5y", "%"]])}</section>
        <section class="detail-section"><h4>人口推移</h4>${rowsOrMissing(detail.population, [["年", "year"], ["人口", "population", "人"], ["人口増減率", "population_change_rate", "%"], ["世帯", "households", "世帯"]])}</section>
        <section class="detail-section"><h4>将来人口</h4>${rowsOrMissing(detail.future_population, [["年", "year"], ["推計人口", "projected_population", "人"], ["2025年比", "retention_rate", "%"]])}</section>
        <section class="detail-section"><h4>生活利便施設</h4>${facilitySummary(detail.facilities)}</section>
        <section class="detail-section"><h4>交通</h4>${transportSummary(detail.transport_summary)}</section>
        <section class="detail-section"><h4>データ出典</h4>${detail.sources?.length ? detail.sources.map((source) => `<div class="metric-row"><a href="${source.source_url}" target="_blank" rel="noreferrer">${source.source_name}</a><span>${source.dataset_id ?? ""}</span></div>`).join("") : `<div class="data-missing">出典データ未生成</div>`}</section>
      </div>`;
  } catch (error) {
    $("#detail-content").innerHTML = `<div class="detail-body"><h3>${basic?.municipality_name ?? areaId}</h3><div class="data-missing">詳細データを読み込めませんでした。</div></div>`;
    console.error(error);
  }
}

async function init() {
  try {
    [state.areas, state.meta] = await Promise.all([
      loadJson("./data/areas.json"),
      loadJson("./data/meta.json").catch(() => null),
    ]);
    $("#area-count").textContent = `対象 ${state.areas.length}区`;
    if (state.meta?.generated_at) {
      const date = new Date(state.meta.generated_at);
      $("#generated-at").textContent = `生成 ${date.toLocaleString("ja-JP")}`;
    }
    setupRanking();
    renderAreaGrid();
    setupCompare();
  } catch (error) {
    $("#area-grid").innerHTML = `<div class="data-missing">サイトデータを生成してください。READMEの手順で ` + "`python scripts/build_site.py`" + ` を実行できます。</div>`;
    console.error(error);
  }
}

$("#search").addEventListener("input", (event) => {
  renderRanking(event.target.value);
  renderAreaGrid(event.target.value);
});
$("#dialog-close").addEventListener("click", () => $("#detail-dialog").close());
$("#detail-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });

document.addEventListener("DOMContentLoaded", init);
