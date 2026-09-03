(() => {
  const areaId = new URLSearchParams(location.search).get("id") || "";
  const target = document.querySelector("#analysis-stat-catalog");
  if (!target || !/^\d{5}$/.test(areaId)) return;

  const sections = [
    ["population_detail", "A", "人口・世帯"],
    ["environment_detail", "B", "自然環境"],
    ["economy_detail", "C", "経済基盤"],
    ["administration_detail", "D", "行政基盤"],
    ["education_detail", "E", "教育"],
    ["labor_detail", "F", "労働"],
    ["culture_detail", "G", "文化・スポーツ"],
    ["housing_detail", "H", "居住"],
    ["health_detail", "I", "健康・医療"],
    ["welfare_detail", "J", "福祉・社会保障"],
  ];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  }

  function format(value, unit) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const number = Number(value);
    const digits = Math.abs(number) >= 100 ? 0 : 2;
    return `${number.toLocaleString("ja-JP", { maximumFractionDigits: digits })}${unit ? ` ${esc(unit)}` : ""}`;
  }

  function latest(rows) {
    const map = new Map();
    for (const row of rows || []) {
      const prev = map.get(row.metric_key);
      if (!prev || String(row.period) >= String(prev.period)) map.set(row.metric_key, row);
    }
    return [...map.values()].sort((a, b) => String(a.metric_key).localeCompare(String(b.metric_key), "ja"));
  }

  function render(payload) {
    const metrics = payload.metrics || {};
    const blocks = sections.map(([category, letter, label]) => {
      const rows = latest(metrics[category]);
      if (!rows.length) return "";
      return `<details class="stat-catalog-section">
        <summary><span>${letter}</span><strong>${esc(label)}</strong><em>${rows.length}指標</em></summary>
        <div class="stat-catalog-body">${rows.map((row) => `
          <div class="analysis-metric-row" title="${esc(row.description)}">
            <div><span>${esc(row.label)}</span><small>${esc(row.period || "—")} / ${esc(row.metric_key)}</small></div>
            <div class="analysis-value"><strong>${format(row.value, row.unit)}</strong>${row.quality_grade ? `<span class="quality-badge quality-${esc(row.quality_grade)}">${esc(row.quality_grade)}</span>` : ""}</div>
          </div>`).join("")}</div>
      </details>`;
    }).filter(Boolean);

    target.innerHTML = blocks.length
      ? `<div class="context-box"><strong>社会・人口統計体系 A〜J</strong><span>各指標は原典ごとに公表年が異なります。既存の主要カードとは別に、取得可能な市区町村数値を網羅的に確認できます。</span></div>${blocks.join("")}`
      : `<div class="data-missing">A〜J公的統計カタログは次回の拡張データ更新後に表示されます。</div>`;
  }

  fetch(`./data/analysis/ward/${areaId}.json`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    })
    .then(render)
    .catch(() => {
      target.innerHTML = `<div class="data-missing">公的統計カタログはまだ生成されていません。</div>`;
    });
})();
