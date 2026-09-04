(() => {
  const areaId = new URLSearchParams(location.search).get("id") || "";
  const target = () => document.querySelector("#analysis-demographics");

  function number(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("ja-JP", { maximumFractionDigits: digits });
  }

  function formatted(row) {
    if (row.value === null || row.value === undefined) return "—";
    if (row.unit === "%") return `${number(row.value, 1)}%`;
    if (row.unit === "人") return `${number(row.value, 0)}人`;
    if (row.unit === "世帯") return `${number(row.value, 0)}世帯`;
    return `${number(row.value, 2)}${row.unit || ""}`;
  }

  function rowHtml(row) {
    const quality = row.quality_grade ? `<span class="quality-badge quality-${row.quality_grade}">${row.quality_grade}</span>` : "";
    return `<div class="analysis-metric-row" title="${row.description || ""}">
      <div><span>${row.label || row.metric_key}</span><small>${row.period || "—"}</small></div>
      <div class="analysis-value"><strong>${formatted(row)}</strong>${quality}</div>
    </div>`;
  }

  async function init() {
    const node = target();
    if (!node || !/^\d{5}$/.test(areaId)) return;
    try {
      const response = await fetch(`./data/analysis/ward/${areaId}.json`, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json();
      const rows = payload.metrics?.demographics || [];
      node.innerHTML = rows.length
        ? rows.map(rowHtml).join("")
        : `<div class="data-missing">人口・世帯構成の詳細は拡張データ更新後に表示されます。</div>`;
    } catch (error) {
      node.innerHTML = `<div class="data-missing">人口・世帯構成データはまだ生成されていません。</div>`;
      console.info("demographics analysis unavailable", error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
