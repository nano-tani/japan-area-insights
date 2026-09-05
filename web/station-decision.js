(() => {
  const shortlist = () => window.StationShortlist;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));

  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  };

  const stationCode = () => {
    const match = window.location.pathname.match(/\/station\/(\d+)\/?$/);
    return match ? match[1] : null;
  };

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function readShortlist() {
    return shortlist()?.read() || [];
  }

  function isSaved(code) {
    return shortlist()?.has(code) || false;
  }

  function toggleStation(station) {
    shortlist()?.toggle(station);
  }

  function compareUrl(items = readShortlist()) {
    return shortlist()?.compareUrl("../../station-compare.html", items) || "../../station-compare.html";
  }

  function propertySearchUrl(name) {
    const stationName = String(name || "").endsWith("駅") ? String(name) : `${String(name || "")}駅`;
    return `https://www.google.com/search?q=${encodeURIComponent(`${stationName} 物件 賃貸 中古マンション`)}`;
  }

  function haversineKm(a, b) {
    const lat1 = Number(a?.latitude);
    const lon1 = Number(a?.longitude);
    const lat2 = Number(b?.latitude);
    const lon2 = Number(b?.longitude);
    if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) return Infinity;
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad;
    const dLon = (lon2 - lon1) * rad;
    const x = Math.sin(dLat / 2) ** 2
      + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  }

  function savedButton(station, extraClass = "") {
    const store = shortlist();
    const saved = isSaved(station.station_code);
    const full = readShortlist().length >= (store?.MAX_ITEMS || 3);
    const disabled = !saved && full;
    return `<button type="button" class="station-save-button ${extraClass}${saved ? " is-saved" : ""}" data-save-station="${escapeHtml(station.station_code)}" ${disabled ? "disabled" : ""} aria-pressed="${saved ? "true" : "false"}">${saved ? "候補に保存済み" : disabled ? "候補は3駅まで" : "候補に保存"}</button>`;
  }

  function renderHeroActions(detail) {
    const heroContent = document.querySelector(".station-page-hero > div");
    if (!heroContent) return;
    let target = document.querySelector("#station-decision-actions");
    if (!target) {
      target = document.createElement("div");
      target.id = "station-decision-actions";
      target.className = "station-decision-actions";
      const meta = heroContent.querySelector(".meta-row");
      if (meta) meta.insertAdjacentElement("afterend", target);
      else heroContent.appendChild(target);
    }
    const items = readShortlist();
    target.innerHTML = `
      ${savedButton(detail, "station-save-primary")}
      <a class="station-compare-link${items.length < 2 ? " is-disabled" : ""}" ${items.length >= 2 ? `href="${compareUrl(items)}"` : 'aria-disabled="true"'}>${items.length >= 2 ? `${items.length}駅を比較` : "2駅保存で比較"}</a>
      <a class="station-property-link" href="${propertySearchUrl(detail.name)}" target="_blank" rel="noreferrer">この駅周辺の物件を検索</a>
      <small>物件検索は外部検索を開きます。特定事業者を優先するリンクではありません。</small>`;
  }

  function nearestStations(current, indexPayload) {
    const rows = (indexPayload?.station_areas || [])
      .filter((station) => String(station.station_code) !== String(current.station_code))
      .map((station) => ({ station, distance: haversineKm(current, station) }))
      .filter((row) => Number.isFinite(row.distance))
      .sort((a, b) => a.distance - b.distance || String(a.station.station_code).localeCompare(String(b.station.station_code)));

    const close = rows.filter((row) => row.distance <= 3.5).slice(0, 4);
    if (close.length >= 4) return close;
    const selected = new Set(close.map((row) => String(row.station.station_code)));
    return close.concat(rows.filter((row) => !selected.has(String(row.station.station_code))).slice(0, 4 - close.length));
  }

  function nearbyCard(row) {
    const station = row.station;
    const score = station.total_score === null || station.total_score === undefined ? "—" : fmt(station.total_score, 1);
    const future = station.future_population_score === null || station.future_population_score === undefined ? "—" : fmt(station.future_population_score, 1);
    return `<article class="station-nearby-card">
      <div class="station-nearby-card-top">
        <div><span>${fmt(row.distance, 1)}km</span><h3>${escapeHtml(station.name)}駅</h3><small>${escapeHtml(station.primary_ward_name || "")}</small></div>
        <strong>${score}<small>/100</small></strong>
      </div>
      <div class="station-nearby-metrics"><span>将来人口スコア <strong>${future}/20</strong></span><span>信頼度 <strong>${escapeHtml(station.confidence || "—")}</strong></span></div>
      <div class="station-nearby-actions">
        <a href="../${escapeHtml(station.station_code)}/">詳しく見る</a>
        ${savedButton(station)}
      </div>
    </article>`;
  }

  function renderSavedSummary() {
    const target = document.querySelector("#station-saved-summary");
    if (!target) return;
    const store = shortlist();
    const items = readShortlist();
    const maxItems = store?.MAX_ITEMS || 3;
    target.innerHTML = `
      <div class="station-saved-head"><strong>保存した候補 ${items.length} / ${maxItems}</strong><span>この端末に保存</span></div>
      <div class="station-saved-chips">
        ${items.length ? items.map((item) => `<button type="button" data-remove-station="${escapeHtml(item.code)}" aria-label="${escapeHtml(item.name)}駅を候補から外す">${escapeHtml(item.name)}駅 <span>×</span></button>`).join("") : "<span>気になる駅を保存すると、ここで比較へ進めます。</span>"}
      </div>
      <div class="station-saved-actions">
        <a class="station-compare-link${items.length < 2 ? " is-disabled" : ""}" ${items.length >= 2 ? `href="${compareUrl(items)}"` : 'aria-disabled="true"'}>${items.length >= 2 ? `${items.length}駅を横並びで比較` : "2駅以上保存すると比較できます"}</a>
        ${items.length ? '<button type="button" data-clear-stations>すべて外す</button>' : ""}
      </div>`;

    target.querySelectorAll("[data-remove-station]").forEach((button) => {
      button.addEventListener("click", () => store?.remove(button.dataset.removeStation));
    });
    target.querySelector("[data-clear-stations]")?.addEventListener("click", () => store?.clear());
  }

  function renderDecisionSection(detail, indexPayload) {
    if (document.querySelector("#station-decision")) return;
    const section = document.createElement("section");
    section.id = "station-decision";
    section.className = "station-section station-decision-section";
    const nearby = nearestStations(detail, indexPayload);
    section.innerHTML = `
      <div class="station-section-head">
        <div><p class="section-kicker">DECIDE & COMPARE</p><h2>近くの候補も見てから決める</h2></div>
        <p>距離だけで決めず、近隣駅の参考スコアや将来人口も並べて候補を残せます。</p>
      </div>
      <div id="station-saved-summary" class="station-saved-summary" aria-live="polite"></div>
      <div class="station-nearby-grid">${nearby.map(nearbyCard).join("")}</div>
      <p class="station-footnote">近隣候補は駅中心点の直線距離が近い順です。徒歩距離・所要時間・路線乗換を表すものではありません。</p>`;

    const nextSection = document.querySelector(".station-link-panel")?.closest(".station-section");
    if (nextSection) nextSection.before(section);
    else document.querySelector("main")?.append(section);
    renderSavedSummary();
  }

  function bindSaveButtons(detail, indexPayload) {
    document.querySelectorAll("[data-save-station]").forEach((button) => {
      if (button.dataset.stationDecisionBound === "true") return;
      button.dataset.stationDecisionBound = "true";
      button.addEventListener("click", () => {
        const code = button.dataset.saveStation;
        const station = String(detail.station_code) === String(code)
          ? detail
          : (indexPayload?.station_areas || []).find((row) => String(row.station_code) === String(code));
        if (station) toggleStation(station);
      });
    });
  }

  function refresh(detail, indexPayload) {
    renderHeroActions(detail);
    renderSavedSummary();
    document.querySelectorAll(".station-nearby-card [data-save-station]").forEach((button) => {
      const station = (indexPayload?.station_areas || []).find((row) => String(row.station_code) === String(button.dataset.saveStation));
      if (!station) return;
      const replacement = document.createElement("div");
      replacement.innerHTML = savedButton(station);
      button.replaceWith(replacement.firstElementChild);
    });
    bindSaveButtons(detail, indexPayload);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const code = stationCode();
    if (!code || !shortlist()) return;
    try {
      const [detail, indexPayload] = await Promise.all([
        loadJson(`../../data/geo/station/${code}.json`),
        loadJson("../../data/geo/index.json"),
      ]);
      renderHeroActions(detail);
      renderDecisionSection(detail, indexPayload);
      bindSaveButtons(detail, indexPayload);
      document.addEventListener("townscore:station-shortlist", () => refresh(detail, indexPayload));
    } catch (error) {
      console.warn("station decision layer unavailable", error);
    }
  });
})();
