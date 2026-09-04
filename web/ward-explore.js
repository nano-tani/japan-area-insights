(() => {
  const areaId = new URLSearchParams(location.search).get("id") || "";
  const target = document.querySelector("#ward-feature-strip");
  const STORAGE_KEY = "town-score-shortlist-v1";
  const MAX_ITEMS = 3;
  let currentWardName = "";

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

  function readShortlist() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(value) ? value.filter((item) => item?.areaId && item?.name).slice(0, MAX_ITEMS) : [];
    } catch (_) {
      return [];
    }
  }

  function writeShortlist(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
    renderShortlistAction();
  }

  function renderShortlistAction() {
    if (!currentWardName) return;
    let action = document.querySelector("#ward-shortlist-action");
    if (!action) {
      action = document.createElement("div");
      action.id = "ward-shortlist-action";
      action.className = "ward-shortlist-action";
      target?.insertAdjacentElement("afterend", action);
    }
    const items = readShortlist();
    const saved = items.some((item) => String(item.areaId) === String(areaId));
    const full = items.length >= MAX_ITEMS && !saved;
    const compareHref = items.length >= 2
      ? `./?compare=${encodeURIComponent(items.map((item) => item.areaId).join(","))}#compare-title`
      : "";
    action.innerHTML = `
      <div><strong>${saved ? "候補に保存済み" : "この街を候補に残す"}</strong><span>${items.length} / ${MAX_ITEMS}地域を保存中</span></div>
      <div class="ward-shortlist-buttons">
        <button type="button" id="ward-shortlist-toggle" ${full ? "disabled" : ""}>${saved ? "候補から外す" : full ? "候補は3件まで" : "+ 候補に残す"}</button>
        ${compareHref ? `<a href="${compareHref}">保存した候補を比較 →</a>` : ""}
      </div>`;
    action.querySelector("#ward-shortlist-toggle")?.addEventListener("click", () => {
      const next = readShortlist();
      const index = next.findIndex((item) => String(item.areaId) === String(areaId));
      if (index >= 0) next.splice(index, 1);
      else if (next.length < MAX_ITEMS) next.push({ areaId: String(areaId), name: currentWardName });
      writeShortlist(next);
    });
  }

  function ensureShortlistStyle() {
    if (document.querySelector("#ward-shortlist-style")) return;
    const style = document.createElement("style");
    style.id = "ward-shortlist-style";
    style.textContent = `
      .ward-shortlist-action{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:12px 0 18px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:#f9fbf9}
      .ward-shortlist-action>div:first-child{display:grid;gap:2px}.ward-shortlist-action strong{font-size:12px}.ward-shortlist-action span{color:var(--muted);font-size:9px}
      .ward-shortlist-buttons{display:flex;align-items:center;gap:8px}.ward-shortlist-buttons button,.ward-shortlist-buttons a{border-radius:999px;padding:7px 10px;font:inherit;font-size:10px;font-weight:800;text-decoration:none}
      .ward-shortlist-buttons button{border:1px solid var(--accent-strong);background:var(--accent-strong);color:#fff;cursor:pointer}.ward-shortlist-buttons button:disabled{opacity:.45;cursor:not-allowed}.ward-shortlist-buttons a{border:1px solid var(--line);background:#fff;color:var(--accent-strong)}
      @media(max-width:620px){.ward-shortlist-action{align-items:flex-start;flex-direction:column}.ward-shortlist-buttons{width:100%;flex-wrap:wrap}.ward-shortlist-buttons button,.ward-shortlist-buttons a{flex:1;text-align:center;white-space:nowrap}}
    `;
    document.head.appendChild(style);
  }

  function renderFromExplore(payload) {
    if (!target) return;
    const ward = (payload.wards || []).find((row) => row.area_id === areaId);
    if (!ward) return;
    currentWardName = ward.municipality_name || "";
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
    renderShortlistAction();
  }

  async function fallback() {
    if (!target || !/^\d{5}$/.test(areaId)) return;
    try {
      const response = await fetch(`./data/area/${areaId}.json`, { cache: "no-store" });
      if (!response.ok) return;
      const area = await response.json();
      currentWardName = area.municipality_name || "";
      const rows = [
        ["総合評価", area.total_score, " / 100"],
        ["価格動向", area.price_score, " / 20"],
        ["将来人口", area.future_population_score, " / 20"],
        ["生活利便性", area.convenience_score, " / 15"],
        ["交通利便性", area.transport_score, " / 15"],
      ];
      target.innerHTML = rows.map(([label, value, suffix]) => `<article class="ward-feature-card"><span>${label}</span><strong>${value ?? "—"}${value === null || value === undefined ? "" : suffix}</strong><small>基本スコア</small></article>`).join("");
      renderShortlistAction();
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
    ensureShortlistStyle();
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
