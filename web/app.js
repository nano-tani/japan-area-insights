const state = { areas: [], meta: null };

const $ = (selector) => document.querySelector(selector);
const score = (value) => value === null || value === undefined ? "—" : Number(value).toFixed(Number(value) % 1 ? 1 : 0);
const confidence = (value) => value || "—";

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

function renderRanking(filter = "") {
  const body = $("#ranking-body");
  const empty = $("#empty-ranking");
  const query = filter.trim().toLowerCase();
  const ranked = state.areas
    .filter((area) => area.total_score !== null && area.total_score !== undefined)
    .filter((area) => area.municipality_name.toLowerCase().includes(query))
    .sort((a, b) => Number(b.total_score) - Number(a.total_score) || a.area_id.localeCompare(b.area_id));

  body.innerHTML = ranked.map((area, index) => `
    <tr data-area-id="${area.area_id}">
      <td>${index + 1}</td>
      <td><strong>${area.municipality_name}</strong></td>
      <td><span class="score-pill">${score(area.total_score)}</span></td>
      <td>${score(area.price_score)}</td>
      <td>${score(area.population_score)}</td>
      <td>${score(area.future_population_score)}</td>
      <td>${confidence(area.confidence)}</td>
    </tr>
  `).join("");

  empty.hidden = ranked.length !== 0;
  body.querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => openDetail(row.dataset.areaId)));
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
  return recent.map((row) => `<div class="metric-row">${columns.map(([label, key]) => `<span>${label}: <strong>${row[key] ?? "—"}</strong></span>`).join("")}</div>`).join("");
}

async function openDetail(areaId) {
  const dialog = $("#detail-dialog");
  const basic = state.areas.find((area) => area.area_id === areaId);
  $("#detail-content").innerHTML = `<div class="detail-body"><p>読み込み中...</p></div>`;
  dialog.showModal();

  try {
    const detail = await loadJson(`./data/area/${areaId}.json`);
    $("#detail-content").innerHTML = `
      <div class="detail-body">
        <p class="section-kicker">AREA ${detail.area_id}</p>
        <h3>${detail.municipality_name}</h3>
        <p class="detail-sub">${detail.prefecture_name} / 対象地域内での相対評価</p>
        <div class="detail-score"><strong>${score(detail.total_score)}</strong><span>/ 100</span></div>
        <div class="metric-row"><span>価格動向</span><strong>${score(detail.price_score)} / 20</strong></div>
        <div class="metric-row"><span>人口動向</span><strong>${score(detail.population_score)} / 20</strong></div>
        <div class="metric-row"><span>将来人口</span><strong>${score(detail.future_population_score)} / 20</strong></div>
        <div class="metric-row"><span>生活利便性</span><strong>${score(detail.convenience_score)} / 15</strong></div>
        <div class="metric-row"><span>交通利便性</span><strong>${score(detail.transport_score)} / 15</strong></div>
        <div class="metric-row"><span>取引活性度</span><strong>${score(detail.transaction_score)} / 10</strong></div>
        <div class="metric-row"><span>データ信頼度</span><strong>${confidence(detail.confidence)}</strong></div>
        <section class="detail-section"><h4>地価推移</h4>${rowsOrMissing(detail.prices, [["年", "year"], ["公示地価", "official_land_price"]])}</section>
        <section class="detail-section"><h4>人口推移</h4>${rowsOrMissing(detail.population, [["年", "year"], ["人口", "population"]])}</section>
        <section class="detail-section"><h4>将来人口</h4>${rowsOrMissing(detail.future_population, [["年", "year"], ["推計人口", "projected_population"]])}</section>
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
    renderRanking();
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
