(() => {
  const baseRenderRanking = renderRanking;
  const maxVisibleResults = 8;

  function normalizeStationTerm(value) {
    return String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "")
      .replace(/駅$/, "");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function matchPriority(station, query) {
    const name = normalizeStationTerm(station.name);
    const ward = normalizeStationTerm(station.primary_ward_name);
    const code = normalizeStationTerm(station.station_code);
    if (name === query) return 0;
    if (name.startsWith(query)) return 1;
    if (name.includes(query)) return 2;
    if (ward.includes(query)) return 3;
    if (code.includes(query)) return 4;
    return 99;
  }

  function matchingStations(query) {
    return stationState.stations
      .map((station) => ({ station, priority: matchPriority(station, query) }))
      .filter(({ priority }) => priority < 99)
      .sort((a, b) => {
        if (a.priority !== b.priority) return a.priority - b.priority;
        const aScore = a.station.total_score == null ? -1 : Number(a.station.total_score);
        const bScore = b.station.total_score == null ? -1 : Number(b.station.total_score);
        if (aScore !== bScore) return bScore - aScore;
        return String(a.station.name).localeCompare(String(b.station.name), "ja");
      });
  }

  function resultCard(station, exact) {
    const total = station.total_score == null ? "—" : score(station.total_score);
    const eligibility = station.eligibility === "eligible"
      ? "総合点算出対象"
      : (station.eligibility_reason || "総合点はデータ不足");
    return `
      <button class="station-search-result${exact ? " is-exact" : ""}" type="button" data-station-code="${escapeHtml(station.station_code)}">
        <span>
          <span class="station-search-result-name">
            <strong>${escapeHtml(station.name)}</strong>
            <span>${escapeHtml(station.primary_ward_name || "")}</span>
          </span>
          <span class="station-search-result-meta">駅中心1km圏 / ${escapeHtml(eligibility)}</span>
        </span>
        <span class="station-search-result-score"><strong>${total}</strong><span>総合 / 100</span></span>
      </button>`;
  }

  function renderImmediateSearchResults() {
    const panel = document.querySelector("#station-search-results");
    const insightStrip = document.querySelector(".insight-strip");
    const input = document.querySelector("#station-search");
    if (!panel || !input) return;

    const rawQuery = input.value.trim();
    const query = normalizeStationTerm(rawQuery);
    if (!query) {
      panel.hidden = true;
      panel.innerHTML = "";
      if (insightStrip) insightStrip.hidden = false;
      return;
    }

    if (insightStrip) insightStrip.hidden = true;
    const matches = matchingStations(query);
    panel.hidden = false;

    if (!matches.length) {
      panel.innerHTML = `
        <div class="station-search-results-head"><h2>検索結果</h2><span>0件</span></div>
        <div class="data-missing">「${escapeHtml(rawQuery)}」に一致する駅はありません。</div>`;
      return;
    }

    const visible = matches.slice(0, maxVisibleResults);
    panel.innerHTML = `
      <div class="station-search-results-head">
        <h2>「${escapeHtml(rawQuery)}」の検索結果</h2>
        <span>${matches.length}件</span>
      </div>
      <div class="station-search-list">
        ${visible.map(({ station, priority }) => resultCard(station, priority === 0)).join("")}
      </div>
      ${matches.length > visible.length ? `<p class="station-search-more">ほか${matches.length - visible.length}件は下のランキング一覧に表示しています。</p>` : ""}`;

    panel.querySelectorAll(".station-search-result").forEach((button) => {
      button.addEventListener("click", () => openStationDetail(button.dataset.stationCode));
    });
  }

  renderRanking = function renderRankingWithImmediateResults(...args) {
    baseRenderRanking(...args);
    renderImmediateSearchResults();
  };
})();
