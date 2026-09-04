(() => {
  const areaId = new URLSearchParams(location.search).get("id") || "";
  const target = document.querySelector("#ward-feature-strip");

  function format(value, unit) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const number = Number(value);
    if (unit === "円/㎡") return `${Math.round(number).toLocaleString("ja-JP")}円/㎡`;
    if (unit === "千円/人") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 0 })}千円/人`;
    if (unit === "%") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}%`;
    if (unit === "点") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}点`;
    return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}${unit || ""}`;
  }

  function highlightLabel(item, direction) {
    if (!item || item.value === null || item.value === undefined) return "データ未生成";
    const pct = direction === "lower" ? item.percentile_low : item.percentile_high;
    if (pct === null || pct === undefined) return item.quality ? `信頼度 ${item.quality}` : "";
    const edge = Math.max(1, Math.min(100, Math.ceil(Number(pct))));
    return direction === "lower" ? `23区内 低い方${edge}%` : `23区内 高い方${edge}%`;
  }

  function renderFromExplore(payload) {
    if (!target) return;
    const ward = (payload.wards || []).find((row) => row.area_id === areaId);
    if (!ward) return;
    const catalog = payload.metric_catalog || {};
    const candidates = [
      "core.total_score",
      "people.retention_2045",
      "economy.taxable_income_per_taxpayer",
      "housing2023.post2011_share",
      "hazard.flood_population_share",
    ];
    target.innerHTML = candidates.map((key) => {
      const meta = catalog[key] || { label: key, unit: "", direction: "neutral" };
      const item = ward.metrics?.[key] || {};
      return `<article class="ward-feature-card">
        <span>${meta.label}</span>
        <strong>${format(item.value, meta.unit)}</strong>
        <small>${highlightLabel(item, meta.direction)}</small>
      </article>`;
    }).join("");
  }

  async function fallback() {
    if (!target || !/^\d{5}$/.test(areaId)) return;
    try {
      const response = await fetch(`./data/area/${areaId}.json`, { cache: "no-store" });
      if (!response.ok) return;
      const area = await response.json();
      const rows = [
        ["総合評価", area.total_score, " / 100"],
        ["価格動向", area.price_score, " / 20"],
        ["将来人口", area.future_population_score, " / 20"],
        ["生活利便性", area.convenience_score, " / 15"],
        ["交通利便性", area.transport_score, " / 15"],
      ];
      target.innerHTML = rows.map(([label, value, suffix]) => `<article class="ward-feature-card"><span>${label}</span><strong>${value ?? "—"}${value === null || value === undefined ? "" : suffix}</strong><small>基本スコア</small></article>`).join("");
    } catch (_) {
      // Detail page remains usable without this optional summary.
    }
  }

  function setupScrollSpy() {
    const nav = document.querySelector(".ward-local-nav");
    if (!nav || !("IntersectionObserver" in window)) return;
    const links = [...nav.querySelectorAll("a[href^='#']")];
    const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      links.forEach((link) => link.classList.toggle("is-active", link.getAttribute("href") === `#${visible.target.id}`));
    }, { rootMargin: "-30% 0px -60%", threshold: [0, .2, .5] });
    sections.forEach((section) => observer.observe(section));
  }

  async function init() {
    if (!/^\d{5}$/.test(areaId)) return;
    try {
      const response = await fetch("./data/explore/wards.json", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      renderFromExplore(await response.json());
    } catch (_) {
      await fallback();
    }
    setupScrollSpy();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
