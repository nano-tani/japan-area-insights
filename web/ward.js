const wardState = { detail: null, map: null, layer: "population_2025" };

const $ = (selector) => document.querySelector(selector);
const score = (value) => value === null || value === undefined ? "—" : Number(value).toFixed(Number(value) % 1 ? 1 : 0);
const number = (value, digits = 0) => value === null || value === undefined ? "—" : Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
const percentText = (value, digits = 1) => value === null || value === undefined ? "—" : `${number(value, digits)}%`;
const yen = (value) => value === null || value === undefined ? "—" : `${number(value)}円/㎡`;
const metricMax = { price_score: 20, population_score: 20, future_population_score: 20, convenience_score: 15, transport_score: 15, transaction_score: 10 };
const facilityLabels = { school: "学校", childcare: "保育園・幼稚園等", medical: "医療機関", library: "図書館", public_facility: "公共施設" };
const MESH_LAT_DEG = 7.5 / 3600;
const MESH_LON_DEG = 11.25 / 3600;

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

function areaIdFromUrl() {
  const value = new URLSearchParams(location.search).get("id") || "";
  return /^\d{5}$/.test(value) ? value : null;
}

function visualMetric(label, value, max) {
  const pct = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, Number(value) / max * 100));
  return `<div class="visual-metric">
    <div class="visual-metric-head"><span>${label}</span><strong>${score(value)} / ${max}</strong></div>
    <div class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></div>
  </div>`;
}

function scoreRing(value) {
  if (value === null || value === undefined) return `<div class="score-ring score-ring-empty"><div class="score-ring-inner"><strong>—</strong><span>/ 100</span></div></div>`;
  const pct = Math.max(0, Math.min(100, Number(value)));
  return `<div class="score-ring ward-ring" style="--score-pct:${pct}%" aria-label="総合スコア ${score(value)}点">
    <div class="score-ring-inner"><strong>${score(value)}</strong><span>/ 100</span></div>
  </div>`;
}

function latest(rows, key) {
  return [...(rows || [])].reverse().find((row) => row[key] !== null && row[key] !== undefined) || null;
}

function futureYear(rows, year) {
  return (rows || []).find((row) => Number(row.year) === Number(year)) || null;
}

function renderHero() {
  const detail = wardState.detail;
  document.title = `${detail.municipality_name} | 街スコア`;
  $("#ward-breadcrumb-name").textContent = detail.municipality_name;
  const missing = detail.total_score === null || detail.total_score === undefined;
  $("#ward-hero").innerHTML = `
    <div class="ward-hero-copy">
      <p class="eyebrow">TOKYO 23 WARDS / AREA ${detail.area_id}</p>
      <h1>${detail.municipality_name}</h1>
      <p class="lead">価格・人口・将来人口・生活・交通・取引を、東京23区内の相対評価と公的データで確認します。</p>
      <div class="meta-row">
        <span>${detail.prefecture_name}</span>
        <span>信頼度 ${detail.confidence ?? "—"}</span>
        <span>スコア版 ${detail.score_version ?? "—"}</span>
      </div>
      ${missing ? `<div class="context-box ward-context">総合点に必要なデータが不足しているため、算出可能な項目だけを表示しています。</div>` : ""}
    </div>
    <div class="ward-hero-score">
      ${scoreRing(detail.total_score)}
      <span>東京23区内での相対評価</span>
    </div>`;
}

function keyStat(label, value, note) {
  return `<article class="key-stat-card"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`;
}

function renderOverview() {
  const detail = wardState.detail;
  const price = latest(detail.prices, "official_land_price") || latest(detail.prices, "prefectural_land_price");
  const pop = latest(detail.population, "population");
  const future2045 = futureYear(detail.future_population, 2045);
  const transport = detail.transport_summary || {};

  $("#ward-key-stats").innerHTML = [
    keyStat("直近の公示・調査地価", yen(price?.official_land_price ?? price?.prefectural_land_price), price ? `${price.year}年` : "データ未生成"),
    keyStat("直近人口", pop ? `${number(pop.population)}人` : "—", pop ? `${pop.year}年 / ${pop.households === null || pop.households === undefined ? "世帯数—" : `${number(pop.households)}世帯`}` : "データ未生成"),
    keyStat("2045年人口維持率", future2045 ? percentText(future2045.retention_rate) : "—", "2025年を100とした推計"),
    keyStat("区内の駅・路線", `${number(transport.station_count)}駅 / ${number(transport.line_count)}路線`, transport.passenger_year ? `乗降客数基準 ${transport.passenger_year}年` : "交通データ"),
  ].join("");

  $("#ward-score-panel").innerHTML = `
    <div class="ward-score-head"><div><span>6 COMPONENTS</span><h3>スコアの内訳</h3></div><strong>${score(detail.total_score)}<small>/100</small></strong></div>
    <div class="score-panel">
      ${visualMetric("価格動向", detail.price_score, 20)}
      ${visualMetric("人口動向", detail.population_score, 20)}
      ${visualMetric("将来人口", detail.future_population_score, 20)}
      ${visualMetric("生活利便性", detail.convenience_score, 15)}
      ${visualMetric("交通利便性", detail.transport_score, 15)}
      ${visualMetric("取引活性度", detail.transaction_score, 10)}
    </div>`;
}

function quantileThresholds(values) {
  const sorted = values.filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number).sort((a, b) => a - b);
  if (!sorted.length) return [];
  return [0.2, 0.4, 0.6, 0.8].map((q) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * q))]);
}

function bucket(value, thresholds) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return -1;
  let index = 0;
  while (index < thresholds.length && Number(value) > thresholds[index]) index += 1;
  return index;
}

function layerLabel(layer) {
  if (layer === "population_2045") return "2045年推計人口";
  if (layer === "retention_2045") return "2045年 / 2025年人口維持率";
  return "2025年推計人口";
}

function layerValue(mesh, layer) {
  return mesh[layer];
}

function meshValueText(mesh, layer) {
  const value = layerValue(mesh, layer);
  return layer === "retention_2045" ? percentText(value) : `${number(value)}人`;
}

function renderMeshDetail(mesh) {
  if (!mesh) return;
  $("#mesh-detail").innerHTML = `
    <p class="section-kicker">MESH ${mesh.mesh_id}</p>
    <h3>${meshValueText(mesh, wardState.layer)}</h3>
    <p class="mesh-detail-label">${layerLabel(wardState.layer)}</p>
    <div class="metric-row"><span>2025年推計人口</span><strong>${number(mesh.population_2025)}人</strong></div>
    <div class="metric-row"><span>2045年推計人口</span><strong>${number(mesh.population_2045)}人</strong></div>
    <div class="metric-row"><span>人口維持率</span><strong>${percentText(mesh.retention_2045)}</strong></div>
    <p class="mesh-detail-note">メッシュ中心: ${Number(mesh.latitude).toFixed(4)}, ${Number(mesh.longitude).toFixed(4)}</p>`;
}

function renderMeshMap() {
  const payload = wardState.map;
  const target = $("#mesh-map");
  if (!payload?.meshes?.length || !payload.bounds) {
    target.innerHTML = `<div class="data-missing">この区の250mメッシュデータはまだ公開スナップショットに含まれていません。次回のデータ更新後に表示されます。</div>`;
    return;
  }

  const meshes = payload.meshes;
  const layer = wardState.layer;
  const thresholds = quantileThresholds(meshes.map((mesh) => layerValue(mesh, layer)));
  const b = payload.bounds;
  const centerLat = (b.north + b.south) / 2;
  const lonFactor = Math.cos(centerLat * Math.PI / 180);
  const geoWidth = Math.max((b.east - b.west) * lonFactor, 0.0001);
  const geoHeight = Math.max(b.north - b.south, 0.0001);
  const width = 1000;
  const height = Math.max(420, Math.min(820, Math.round(width * geoHeight / geoWidth)));
  const scaleX = width / geoWidth;
  const scaleY = height / geoHeight;
  const cellW = Math.max(1.2, MESH_LON_DEG * lonFactor * scaleX + 0.4);
  const cellH = Math.max(1.2, MESH_LAT_DEG * scaleY + 0.4);
  const opacities = [0.16, 0.30, 0.46, 0.64, 0.86];

  const cells = meshes.map((mesh, index) => {
    const x = (mesh.longitude - b.west) * lonFactor * scaleX - cellW / 2;
    const y = (b.north - mesh.latitude) * scaleY - cellH / 2;
    const band = bucket(layerValue(mesh, layer), thresholds);
    const opacity = band < 0 ? 0.05 : opacities[band];
    return `<rect class="mesh-cell" data-mesh-index="${index}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellW.toFixed(2)}" height="${cellH.toFixed(2)}" fill="var(--accent)" fill-opacity="${opacity}">
      <title>${mesh.mesh_id} / ${layerLabel(layer)} ${meshValueText(mesh, layer)}</title>
    </rect>`;
  }).join("");

  const stations = (payload.stations || []).filter((station) =>
    station.longitude >= b.west && station.longitude <= b.east && station.latitude >= b.south && station.latitude <= b.north
  ).map((station) => {
    const x = (station.longitude - b.west) * lonFactor * scaleX;
    const y = (b.north - station.latitude) * scaleY;
    return `<circle class="mesh-station" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4.5"><title>${station.name}</title></circle>`;
  }).join("");

  target.innerHTML = `<svg class="mesh-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${wardState.detail.municipality_name} ${layerLabel(layer)} 250mメッシュマップ">
    <g>${cells}</g><g>${stations}</g>
  </svg>`;

  target.querySelectorAll(".mesh-cell").forEach((cell) => {
    cell.addEventListener("click", () => {
      target.querySelectorAll(".mesh-cell.is-selected").forEach((selected) => selected.classList.remove("is-selected"));
      cell.classList.add("is-selected");
      renderMeshDetail(meshes[Number(cell.dataset.meshIndex)]);
    });
  });

  const summary = payload.summary || {};
  $("#mesh-detail").innerHTML = `
    <p class="section-kicker">AREA SUMMARY</p>
    <h3>${payload.summary?.mesh_count ?? meshes.length}メッシュ</h3>
    <p>${layerLabel(layer)}を濃淡で表示しています。</p>
    <div class="metric-row"><span>2025年合計</span><strong>${number(summary.population_2025_total)}人</strong></div>
    <div class="metric-row"><span>2045年合計</span><strong>${number(summary.population_2045_total)}人</strong></div>
    <div class="metric-row"><span>区全体の維持率</span><strong>${percentText(summary.retention_2045_area)}</strong></div>
    <div class="metric-row"><span>駅表示</span><strong>${number(payload.stations?.length || 0)}駅</strong></div>
    <p class="mesh-detail-note">セルを選択すると個別値を確認できます。</p>`;
}

function timeline(rows, key, formatter, limit = 7) {
  const valid = (rows || []).filter((row) => row[key] !== null && row[key] !== undefined).slice(-limit);
  if (!valid.length) return `<div class="data-missing">データ未生成</div>`;
  const max = Math.max(...valid.map((row) => Number(row[key])), 1);
  return `<div class="timeline">${valid.map((row) => {
    const width = Math.max(3, Number(row[key]) / max * 100);
    return `<div class="timeline-row"><span>${row.year}</span><div class="timeline-bar"><i style="width:${width}%"></i></div><strong>${formatter(row[key], row)}</strong></div>`;
  }).join("")}</div>`;
}

function renderTrends() {
  const detail = wardState.detail;
  const priceRows = (detail.prices || []).filter((row) => row.official_land_price !== null && row.official_land_price !== undefined);
  $("#ward-price-trend").innerHTML = timeline(priceRows, "official_land_price", (value, row) => `${number(value)}円/㎡${row.yoy_change === null || row.yoy_change === undefined ? "" : ` / ${percentText(row.yoy_change)}`}`);
  $("#ward-population-trend").innerHTML = timeline(detail.population, "population", (value, row) => `${number(value)}人${row.population_change_rate === null || row.population_change_rate === undefined ? "" : ` / ${percentText(row.population_change_rate)}`}`);
  $("#ward-future-trend").innerHTML = timeline(detail.future_population, "projected_population", (value, row) => `${number(value)}人 / ${percentText(row.retention_rate)}`, 10);
}

function renderLifeAccess() {
  const detail = wardState.detail;
  const byType = Object.fromEntries((detail.facilities || []).map((row) => [row.facility_type, row.count]));
  $("#ward-facilities").innerHTML = Object.entries(facilityLabels).map(([key, label]) => `<div class="metric-row"><span>${label}</span><strong>${number(byType[key] ?? 0)}施設</strong></div>`).join("") || `<div class="data-missing">データ未生成</div>`;

  const t = detail.transport_summary || {};
  $("#ward-transport").innerHTML = `
    <div class="metric-row"><span>駅数</span><strong>${number(t.station_count)}駅</strong></div>
    <div class="metric-row"><span>路線数</span><strong>${number(t.line_count)}路線</strong></div>
    <div class="metric-row"><span>駅別乗降客数 合計</span><strong>${t.passenger_count === null || t.passenger_count === undefined ? "—" : `${number(t.passenger_count)}人/日`}</strong></div>
    <div class="metric-row"><span>乗降客数 基準年</span><strong>${t.passenger_year ?? "—"}年</strong></div>`;

  const names = [...new Set((detail.stations || []).map((row) => row.station_name).filter(Boolean))].slice(0, 18);
  $("#ward-stations").innerHTML = names.length ? names.map((name) => `<span class="station-chip">${name}</span>`).join("") : `<div class="data-missing">駅データ未生成</div>`;
}

function renderSources() {
  const rows = wardState.detail.sources || [];
  $("#ward-sources").innerHTML = rows.length ? rows.map((source) => `
    <a class="source-card" href="${source.source_url}" target="_blank" rel="noreferrer">
      <span>${source.source_name}</span><strong>${source.dataset_id ?? "データセット"}</strong><small>出典を開く →</small>
    </a>`).join("") : `<div class="data-missing">出典データ未生成</div>`;
}

async function init() {
  const areaId = areaIdFromUrl();
  if (!areaId) {
    $("#ward-hero").innerHTML = `<div class="data-missing">区IDが指定されていません。<a href="./">東京23区一覧へ戻る</a></div>`;
    return;
  }

  try {
    const [detail, map] = await Promise.all([
      loadJson(`./data/area/${areaId}.json`),
      loadJson(`./data/map/ward/${areaId}/mesh250.json`).catch(() => null),
    ]);
    wardState.detail = detail;
    wardState.map = map;
    renderHero();
    renderOverview();
    renderMeshMap();
    renderTrends();
    renderLifeAccess();
    renderSources();
    $("#mesh-layer").addEventListener("change", (event) => {
      wardState.layer = event.target.value;
      renderMeshMap();
    });
  } catch (error) {
    console.error(error);
    $("#ward-hero").innerHTML = `<div class="data-missing">区詳細データを読み込めませんでした。<a href="./">東京23区一覧へ戻る</a></div>`;
  }
}

document.addEventListener("DOMContentLoaded", init);
