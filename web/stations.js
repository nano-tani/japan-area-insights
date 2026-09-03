const stationState = { stations: [], meta: null, rankingMetric: "total_score" };

const $ = (selector) => document.querySelector(selector);
const score = (value) => value === null || value === undefined ? "—" : Number(value).toFixed(Number(value) % 1 ? 1 : 0);
const number = (value, digits = 0) => value === null || value === undefined ? "—" : Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
const metricLabels = {
  total_score: "総合",
  price_score: "価格動向",
  population_score: "人口動向（推計）",
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

function stationLabel(station) {
  const ward = station.primary_ward_name ? ` / ${station.primary_ward_name}` : "";
  return `${station.name}${ward}`;
}

function chooseInitialMetric() {
  const candidates = [
    "total_score", "price_score", "population_score", "future_population_score",
    "convenience_score", "transport_score", "transaction_score"
  ];
  return candidates.find((key) => stationState.stations.some((station) => station[key] !== null && station[key] !== undefined)) || "total_score";
}

function filteredStations() {
  const query = $("#station-search").value.trim().toLowerCase();
  if (!query) return stationState.stations;
  return stationState.stations.filter((station) =>
    `${station.name} ${station.primary_ward_name ?? ""} ${station.station_code}`.toLowerCase().includes(query)
  );
}

function renderRanking() {
  const metric = stationState.rankingMetric;
  const ranked = filteredStations()
    .filter((station) => station[metric] !== null && station[metric] !== undefined)
    .sort((a, b) => Number(b[metric]) - Number(a[metric]) || a.station_code.localeCompare(b.station_code));

  $("#station-ranking-score-label").textContent = metricLabels[metric] || "評価";
  $("#station-ranking-body").innerHTML = ranked.map((station, index) => `
    <tr data-station-code="${station.station_code}">
      <td>${index + 1}</td>
      <td><strong>${station.name}</strong><br><small>${station.primary_ward_name ?? ""}</small></td>
      <td><span class="score-pill">${score(station[metric])}</span></td>
      <td>${score(station.price_score)}</td>
      <td>${score(station.population_score)}</td>
      <td>${score(station.future_population_score)}</td>
      <td>${score(station.convenience_score)}</td>
      <td>${score(station.transport_score)}</td>
      <td>${score(station.transaction_score)}</td>
      <td>${station.confidence ?? "—"}</td>
    </tr>
  `).join("");

  $("#station-empty-ranking").hidden = ranked.length !== 0;
  $("#station-ranking-body").querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", () => openStationDetail(row.dataset.stationCode));
  });
}

function compareCard(station) {
  const eligibility = station.eligibility === "eligible"
    ? "総合点算出対象"
    : (station.eligibility_reason || "総合点: データ不足");
  const metrics = [
    ["総合", station.total_score],
    ["価格動向", station.price_score],
    ["人口動向（推計）", station.population_score],
    ["将来人口", station.future_population_score],
    ["生活利便性", station.convenience_score],
    ["交通利便性", station.transport_score],
    ["取引活性度", station.transaction_score],
  ];
  return `<article class="compare-card">
    <h3>${station.name}</h3>
    <p class="detail-sub">${station.primary_ward_name ?? ""} / 駅中心1km圏</p>
    ${metrics.map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${score(value)}</strong></div>`).join("")}
    <div class="metric-row"><span>信頼度</span><strong>${station.confidence ?? "—"}</strong></div>
    <div class="data-missing" style="margin-top:12px">${eligibility}</div>
  </article>`;
}

function setupCompare() {
  const options = stationState.stations.map((station) =>
    `<option value="${station.station_code}">${stationLabel(station)}</option>`
  ).join("");
  $("#station-compare-a").innerHTML = options;
  $("#station-compare-b").innerHTML = options;
  if (stationState.stations.length > 1) $("#station-compare-b").selectedIndex = 1;
  $("#station-compare-a").addEventListener("change", renderCompare);
  $("#station-compare-b").addEventListener("change", renderCompare);
  renderCompare();
}

function renderCompare() {
  const a = stationState.stations.find((station) => station.station_code === $("#station-compare-a").value);
  const b = stationState.stations.find((station) => station.station_code === $("#station-compare-b").value);
  if (!a || !b) {
    $("#station-compare-grid").innerHTML = `<div class="data-missing">駅エリアデータ未生成</div>`;
    return;
  }
  $("#station-compare-grid").innerHTML = compareCard(a) + compareCard(b);
}

function metric(detail, key) {
  return detail.metrics?.[key]?.value ?? null;
}

function futureSummary(rows) {
  if (!rows?.length) return `<div class="data-missing">データ未生成</div>`;
  const targets = rows.filter((row) => [2020, 2025, 2030, 2035, 2040, 2045].includes(Number(row.year)));
  return targets.map((row) => `
    <div class="metric-row">
      <span>${row.year}年</span>
      <strong>${number(row.projected_population)}人 / 2025年比 ${number(row.retention_rate, 1)}%</strong>
    </div>
  `).join("");
}

function transactionSummary(rows) {
  if (!rows?.length) return `<div class="data-missing">駅指定取引データ未生成</div>`;
  return rows.slice(-6).reverse().map((row) => `
    <div class="metric-row">
      <span>${row.year}年 / ${row.transaction_count}件</span>
      <strong>中央値 ${row.median_unit_price === null ? "—" : `${number(row.median_unit_price)}円/㎡`}</strong>
    </div>
  `).join("");
}

async function openStationDetail(stationCode) {
  const dialog = $("#station-detail-dialog");
  $("#station-detail-content").innerHTML = `<div class="detail-body"><p>読み込み中...</p></div>`;
  dialog.showModal();

  try {
    const detail = await loadJson(`./data/geo/station/${stationCode}.json`);
    const total = detail.total_score === null || detail.total_score === undefined
      ? `<div class="data-missing">総合点は未算出です。${detail.eligibility_reason ?? "必要データが不足しています。"}</div>`
      : `<div class="detail-score"><strong>${score(detail.total_score)}</strong><span>/ 100</span></div>`;
    const lines = detail.lines?.length
      ? [...new Set(detail.lines.map((row) => `${row.operator_name ?? ""} ${row.line_name ?? ""}`.trim()))].join(" / ")
      : "—";

    const facilities = Object.entries(facilityLabels).map(([key, label]) => `
      <div class="metric-row"><span>${label}</span><strong>${number(metric(detail, `facility_${key}_count`))}施設</strong></div>
    `).join("");

    $("#station-detail-content").innerHTML = `
      <div class="detail-body">
        <p class="section-kicker">STATION ${detail.station_code}</p>
        <h3>${detail.name}</h3>
        <p class="detail-sub">${detail.primary_ward_name ?? ""} / 駅中心 ${detail.radius_m ?? 1000}m / ${detail.mesh_count ?? 0}メッシュ</p>
        <p class="detail-sub">${lines}</p>
        ${total}
        <div class="metric-row"><span>価格動向</span><strong>${score(detail.price_score)} / 20</strong></div>
        <div class="metric-row"><span>人口動向（2020→2025推計）</span><strong>${score(detail.population_score)} / 20</strong></div>
        <div class="metric-row"><span>将来人口</span><strong>${score(detail.future_population_score)} / 20</strong></div>
        <div class="metric-row"><span>生活利便性</span><strong>${score(detail.convenience_score)} / 15</strong></div>
        <div class="metric-row"><span>交通利便性</span><strong>${score(detail.transport_score)} / 15</strong></div>
        <div class="metric-row"><span>取引活性度</span><strong>${score(detail.transaction_score)} / 10</strong></div>
        <div class="metric-row"><span>データ信頼度</span><strong>${detail.confidence ?? "—"}</strong></div>

        <section class="detail-section"><h4>人口・将来人口</h4>
          <div class="metric-row"><span>2020→2025推計変化</span><strong>${number(metric(detail, "population_change_2020_2025_projection"), 1)}%</strong></div>
          <div class="metric-row"><span>2045年 / 2025年 人口維持率</span><strong>${number(metric(detail, "future_population_retention_2045"), 1)}%</strong></div>
          ${futureSummary(detail.future_population)}
        </section>

        <section class="detail-section"><h4>生活利便施設</h4>${facilities}</section>

        <section class="detail-section"><h4>交通</h4>
          <div class="metric-row"><span>1km圏の駅数</span><strong>${number(metric(detail, "nearby_station_count"))}駅</strong></div>
          <div class="metric-row"><span>1km圏の路線数</span><strong>${number(metric(detail, "nearby_line_count"))}路線</strong></div>
          <div class="metric-row"><span>駅別乗降客数 合計</span><strong>${number(metric(detail, "ridership_daily"))}人/日</strong></div>
        </section>

        <section class="detail-section"><h4>駅指定の取引価格</h4>
          <div class="data-missing">ここは1km圏内の物件位置を推測した集計ではありません。XIT001をこの駅のグループコードで検索した取引です。</div>
          ${transactionSummary(detail.transactions)}
        </section>

        <section class="detail-section"><h4>データ出典</h4>${detail.sources?.length ? detail.sources.map((source) => `
          <div class="metric-row"><a href="${source.source_url}" target="_blank" rel="noreferrer">${source.source_name}</a><span>${source.dataset_id ?? ""}</span></div>
        `).join("") : `<div class="data-missing">出典データ未生成</div>`}</section>
      </div>`;
  } catch (error) {
    $("#station-detail-content").innerHTML = `<div class="detail-body"><div class="data-missing">駅詳細データを読み込めませんでした。</div></div>`;
    console.error(error);
  }
}

async function init() {
  try {
    stationState.meta = await loadJson("./data/geo/index.json");
    stationState.stations = stationState.meta.station_areas || [];
    $("#station-count").textContent = `対象 ${stationState.stations.length}駅`;
    if (stationState.meta.generated_at) {
      $("#station-generated-at").textContent = `生成 ${new Date(stationState.meta.generated_at).toLocaleString("ja-JP")}`;
    }
    stationState.rankingMetric = chooseInitialMetric();
    $("#station-ranking-metric").value = stationState.rankingMetric;
    $("#station-ranking-metric").addEventListener("change", (event) => {
      stationState.rankingMetric = event.target.value;
      renderRanking();
    });
    $("#station-search").addEventListener("input", renderRanking);
    renderRanking();
    setupCompare();
  } catch (error) {
    $("#station-count").textContent = "対象 0駅";
    $("#station-ranking-body").innerHTML = "";
    $("#station-empty-ranking").hidden = false;
    $("#station-compare-grid").innerHTML = `<div class="data-missing">駅エリアデータは次回の公開データ更新後に生成されます。</div>`;
    console.error(error);
  }
}

$("#station-dialog-close").addEventListener("click", () => $("#station-detail-dialog").close());
$("#station-detail-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

document.addEventListener("DOMContentLoaded", init);
