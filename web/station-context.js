(() => {
  const metric = (detail, key) => detail?.metrics?.[key]?.value ?? null;
  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  };

  const stationCode = () => {
    const match = window.location.pathname.match(/\/station\/(\d+)\/?$/);
    return match ? match[1] : null;
  };

  async function json(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function card(label, value, unit, note = "") {
    return `<article class="station-context-card"><span>${label}</span><strong>${value}${unit}</strong>${note ? `<small>${note}</small>` : ""}</article>`;
  }

  function contextCards(detail, mesh) {
    const summary = mesh?.summary || {};
    const terrain = summary.terrain || {};
    const seismic = summary.seismic || {};
    const flood = metric(detail, "hazard_flood_population_share");
    const flood3 = metric(detail, "hazard_flood_3m_plus_population_share");
    const liquefaction = metric(detail, "hazard_liquefaction_population_share");
    const quake = metric(detail, "seismic_30y_6lower_probability")
      ?? seismic.earthquake_probability_30y_6lower_population_weighted;
    const elevation = metric(detail, "terrain_elevation_population_weighted_mean")
      ?? terrain.elevation_population_weighted_mean;
    const low5 = metric(detail, "terrain_population_below_5m_share")
      ?? terrain.population_below_5m_share;

    const rows = [
      flood !== null ? card("洪水浸水想定区域", fmt(flood), "%", "2025推計人口の区域曝露") : "",
      flood3 !== null ? card("洪水 3m以上", fmt(flood3), "%", "2025推計人口の区域曝露") : "",
      liquefaction !== null ? card("液状化傾向区域", fmt(liquefaction), "%", "2025推計人口の区域曝露") : "",
      quake !== null ? card("30年 震度6弱以上", fmt(quake), "%", "J-SHIS・人口加重") : "",
      elevation !== null ? card("人口加重平均標高", fmt(elevation), "m", "250mメッシュ中心") : "",
      low5 !== null ? card("標高5m未満人口", fmt(low5), "%", "標高取得済みメッシュ内") : "",
    ].filter(Boolean);
    return rows.join("");
  }

  const layerMeta = {
    retention_2045: {
      label: "2045人口維持率",
      value: (m) => m.retention_2045,
      text: (v) => `${fmt(v)}%`,
      levels: [80, 95, 105],
      legend: "色は2025年比の人口維持率。濃いほど値が高い。",
    },
    elevation_m: {
      label: "標高",
      value: (m) => m.elevation_m,
      text: (v) => `${fmt(v)}m`,
      levels: [5, 15, 30],
      legend: "250mメッシュ中心点の標高。濃いほど標高値が高い。",
    },
    earthquake_probability_30y_6lower: {
      label: "震度6弱以上",
      value: (m) => m.earthquake_probability_30y_6lower,
      text: (v) => `${fmt(v)}%`,
      levels: [20, 40, 60],
      legend: "J-SHISの今後30年・震度6弱以上確率。濃いほど確率値が高い。",
    },
  };

  function level(value, cuts) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "missing";
    const v = Number(value);
    if (v < cuts[0]) return "1";
    if (v < cuts[1]) return "2";
    if (v < cuts[2]) return "3";
    return "4";
  }

  function renderMeshGrid(mesh, layerKey) {
    const target = document.querySelector("#station-mesh-grid");
    const legend = document.querySelector("#station-mesh-legend");
    if (!target || !legend) return;
    const rows = mesh?.meshes || [];
    const meta = layerMeta[layerKey];
    if (!rows.length || !meta) {
      target.innerHTML = '<div class="station-context-empty">250mメッシュデータ未生成</div>';
      return;
    }

    const lons = [...new Set(rows.map((row) => Number(row.longitude).toFixed(7)))].map(Number).sort((a, b) => a - b);
    const lats = [...new Set(rows.map((row) => Number(row.latitude).toFixed(7)))].map(Number).sort((a, b) => b - a);
    const lonIndex = new Map(lons.map((value, index) => [value.toFixed(7), index + 1]));
    const latIndex = new Map(lats.map((value, index) => [value.toFixed(7), index + 1]));
    target.style.gridTemplateColumns = `repeat(${lons.length}, minmax(20px, 1fr))`;
    target.innerHTML = rows.map((row) => {
      const value = meta.value(row);
      const text = meta.text(value);
      const col = lonIndex.get(Number(row.longitude).toFixed(7));
      const gridRow = latIndex.get(Number(row.latitude).toFixed(7));
      const title = `${meta.label}: ${text} / 2025人口 ${fmt(row.population_2025, 0)}人`;
      return `<button class="station-mesh-cell level-${level(value, meta.levels)}" style="grid-column:${col};grid-row:${gridRow}" type="button" title="${title}" aria-label="${title}"><span>${text}</span></button>`;
    }).join("");
    legend.textContent = meta.legend;
  }

  function buildSection(detail, mesh) {
    const cards = contextCards(detail, mesh);
    const section = document.createElement("section");
    section.className = "station-section station-context-section";
    section.id = "station-context";
    section.innerHTML = `
      <div class="station-section-head">
        <div><p class="section-kicker">HAZARD & TERRAIN</p><h2>防災・地形を1km圏で見る</h2></div>
        <p>駅1km圏の250mメッシュ代表値と公的ハザード区域の重なりです。個別物件の安全性を判定するものではありません。</p>
      </div>
      ${cards ? `<div class="station-context-grid">${cards}</div>` : ""}
      <div class="station-context-map-panel">
        <div class="station-context-toolbar" role="group" aria-label="250mメッシュ表示項目">
          ${Object.entries(layerMeta).map(([key, meta], index) =>
            `<button type="button" data-mesh-layer="${key}"${index === 0 ? ' aria-pressed="true"' : ' aria-pressed="false"'}>${meta.label}</button>`
          ).join("")}
        </div>
        <div id="station-mesh-grid" class="station-mesh-grid" aria-label="駅1km圏250mメッシュ"></div>
        <p id="station-mesh-legend" class="station-mesh-legend"></p>
      </div>
      <div class="station-notice">
        <strong>読み方</strong>
        <span>区域曝露は250mメッシュ中心が公式区域に入るかで集計します。標高・地震も250m代表値です。住居を決める際は住所・物件単位の公式ハザード情報も確認してください。</span>
      </div>`;
    const score = document.querySelector("#score-heading")?.closest(".station-section");
    if (score) score.before(section);
    else document.querySelector("main")?.append(section);

    section.querySelectorAll("[data-mesh-layer]").forEach((button) => {
      button.addEventListener("click", () => {
        section.querySelectorAll("[data-mesh-layer]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        renderMeshGrid(mesh, button.dataset.meshLayer);
      });
    });
    renderMeshGrid(mesh, "retention_2045");
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const code = stationCode();
    if (!code) return;
    try {
      const [detail, mesh] = await Promise.all([
        json(`../../data/geo/station/${code}.json`),
        json(`../../data/map/station/${code}/mesh250.json`),
      ]);
      buildSection(detail, mesh);
    } catch (error) {
      console.warn("station context unavailable", error);
    }
  });
})();
