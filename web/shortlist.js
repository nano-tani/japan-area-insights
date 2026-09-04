(() => {
  const STORAGE_KEY = "town-score-shortlist-v1";
  const MAX_ITEMS = 3;
  const state = { areas: [], explore: null };
  let compareSyncQueued = false;

  const LABEL_OVERRIDES = {
    "household.single_household_share": "1人世帯比率",
    "people.child_share": "子ども人口比率",
    "people.elderly_share": "高齢者人口比率",
    "demographics.natural_change": "出生死亡差",
  };

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
  }

  function readShortlist() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((item) => item && item.areaId && item.name)
        .slice(0, MAX_ITEMS)
        .map((item) => ({ areaId: String(item.areaId), name: String(item.name) }));
    } catch (_) {
      return [];
    }
  }

  function writeShortlist(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
    document.dispatchEvent(new CustomEvent("townscore:shortlist", { detail: readShortlist() }));
  }

  function isSaved(areaId) {
    return readShortlist().some((item) => item.areaId === String(areaId));
  }

  function setPanelMessage(message) {
    const target = document.querySelector("#shortlist-message");
    if (!target) return;
    target.textContent = message;
  }

  function toggle(areaId, name) {
    const items = readShortlist();
    const id = String(areaId);
    const index = items.findIndex((item) => item.areaId === id);
    if (index >= 0) {
      items.splice(index, 1);
      writeShortlist(items);
      setPanelMessage(`${name}を候補から外しました。`);
      return;
    }
    if (items.length >= MAX_ITEMS) {
      setPanelMessage("候補は3地域までです。1地域外してから追加してください。");
      return;
    }
    items.push({ areaId: id, name: String(name) });
    writeShortlist(items);
    setPanelMessage(`${name}を候補に追加しました。`);
  }

  function ensureShortlistPanel() {
    if (document.querySelector("#shortlist-bar")) return;
    const results = document.querySelector("#recommend-results");
    if (!results) return;
    const panel = document.createElement("div");
    panel.id = "shortlist-bar";
    panel.className = "shortlist-panel";
    panel.setAttribute("aria-live", "polite");
    results.insertAdjacentElement("afterend", panel);
  }

  function renderShortlistPanel() {
    ensureShortlistPanel();
    const target = document.querySelector("#shortlist-bar");
    if (!target) return;
    const items = readShortlist();
    target.innerHTML = `
      <div class="shortlist-panel-head">
        <div><span>SHORTLIST</span><strong>気になる街 ${items.length} / ${MAX_ITEMS}</strong></div>
        <small>この端末だけに保存します</small>
      </div>
      <div class="shortlist-items">
        ${items.length ? items.map((item) => `
          <button type="button" class="shortlist-chip" data-shortlist-remove="${escapeHtml(item.areaId)}" aria-label="${escapeHtml(item.name)}を候補から外す">
            ${escapeHtml(item.name)} <span>×</span>
          </button>`).join("") : `<span class="shortlist-empty">おすすめ結果から「候補に残す」を押してください。</span>`}
      </div>
      <div class="shortlist-actions">
        <button type="button" id="shortlist-compare" class="shortlist-compare" ${items.length < 2 ? "disabled" : ""}>${items.length >= 2 ? `${items.length}地域を比較する` : "2地域以上で比較"}</button>
        <button type="button" id="shortlist-clear" class="shortlist-clear" ${items.length ? "" : "disabled"}>候補をクリア</button>
        <span id="shortlist-message">${items.length === MAX_ITEMS ? "3地域まで選択済みです。" : "最大3地域まで残せます。"}</span>
      </div>`;

    target.querySelectorAll("[data-shortlist-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        const item = items.find((row) => row.areaId === button.dataset.shortlistRemove);
        if (item) toggle(item.areaId, item.name);
      });
    });
    target.querySelector("#shortlist-clear")?.addEventListener("click", () => {
      writeShortlist([]);
      setPanelMessage("候補をクリアしました。");
    });
    target.querySelector("#shortlist-compare")?.addEventListener("click", compareShortlist);
    updateRecommendationButtons();
  }

  function areaIdFromCard(card) {
    try {
      return new URL(card.href, location.href).searchParams.get("id");
    } catch (_) {
      return null;
    }
  }

  function enhanceRecommendationCards() {
    document.querySelectorAll("a.recommend-card:not([data-shortlist-enhanced])").forEach((card) => {
      const areaId = areaIdFromCard(card);
      const name = card.querySelector("h4")?.textContent?.trim();
      if (!areaId || !name) return;
      card.dataset.shortlistEnhanced = "true";
      const wrapper = document.createElement("div");
      wrapper.className = "recommend-card-wrap";
      card.insertAdjacentElement("beforebegin", wrapper);
      wrapper.appendChild(card);

      const reasonBox = card.querySelector(".recommend-reasons");
      if (reasonBox && !card.querySelector(".recommend-reasons-label")) {
        reasonBox.insertAdjacentHTML("beforebegin", `<span class="recommend-reasons-label">合っている理由</span>`);
      }
      const weak = card.querySelector(".recommend-weak");
      if (weak && !weak.querySelector("strong")) {
        weak.innerHTML = `<strong>確認しておきたい点</strong><span>${escapeHtml(weak.textContent.replace(/^注意:\s*/, ""))}</span>`;
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "shortlist-save";
      button.dataset.shortlistToggle = areaId;
      button.dataset.shortlistName = name;
      button.addEventListener("click", () => toggle(areaId, name));
      wrapper.appendChild(button);
    });
    updateRecommendationButtons();
  }

  function updateRecommendationButtons() {
    const items = readShortlist();
    const full = items.length >= MAX_ITEMS;
    document.querySelectorAll("[data-shortlist-toggle]").forEach((button) => {
      const saved = items.some((item) => item.areaId === String(button.dataset.shortlistToggle));
      button.classList.toggle("is-saved", saved);
      button.disabled = !saved && full;
      button.textContent = saved ? "✓ 候補に保存済み" : full ? "候補は3件まで" : "+ 候補に残す";
      button.setAttribute("aria-pressed", saved ? "true" : "false");
    });
  }

  function score(value) {
    if (value === null || value === undefined) return "—";
    const number = Number(value);
    return number.toFixed(number % 1 ? 1 : 0);
  }

  function percent(value, max) {
    if (value === null || value === undefined || !max) return 0;
    return Math.max(0, Math.min(100, Number(value) / max * 100));
  }

  function visualMetric(label, value, max) {
    return `<div class="visual-metric">
      <div class="visual-metric-head"><span>${escapeHtml(label)}</span><strong>${score(value)} / ${max}</strong></div>
      <div class="bar-track"><span class="bar-fill" style="width:${percent(value, max)}%"></span></div>
    </div>`;
  }

  function thirdBasicCard(area) {
    return `<article class="compare-card shortlist-third-basic" data-shortlist-third="${escapeHtml(area.area_id)}">
      <div class="compare-card-top">
        <div><span class="pref">東京都</span><h3>${escapeHtml(area.municipality_name)}</h3></div>
        <div class="compare-score"><strong>${score(area.total_score)}</strong><span>総合 / 100</span></div>
      </div>
      ${visualMetric("価格動向", area.price_score, 20)}
      ${visualMetric("人口動向", area.population_score, 20)}
      ${visualMetric("将来人口", area.future_population_score, 20)}
      ${visualMetric("生活利便性", area.convenience_score, 15)}
      ${visualMetric("交通利便性", area.transport_score, 15)}
      ${visualMetric("取引活性度", area.transaction_score, 10)}
      <div class="metric-row"><span>データ信頼度</span><strong>${escapeHtml(area.confidence || "—")}</strong></div>
    </article>`;
  }

  function catalog(key) {
    return state.explore?.metric_catalog?.[key] || { label: LABEL_OVERRIDES[key] || key, unit: "" };
  }

  function formatDetailValue(key, value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const unit = catalog(key).unit || "";
    const number = Number(value);
    if (unit === "円/㎡") return `${Math.round(number).toLocaleString("ja-JP")}円/㎡`;
    if (unit === "千円/人") return `${Math.round(number).toLocaleString("ja-JP")}千円/人`;
    if (["人", "件", "戸", "事業所", "施設", "世帯"].includes(unit)) return `${Math.round(number).toLocaleString("ja-JP")}${unit}`;
    if (unit === "%") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}%`;
    if (unit === "点") return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}点`;
    return `${number.toLocaleString("ja-JP", { maximumFractionDigits: 2 })}${unit}`;
  }

  function thirdDetailCard(ward, theme) {
    return `<article class="compare-detail-card shortlist-third-detail" data-shortlist-third-detail="${escapeHtml(ward.area_id)}:${escapeHtml(theme.key)}">
      <div class="compare-detail-head"><span>${escapeHtml(theme.label)}</span><h3>${escapeHtml(ward.municipality_name)}</h3></div>
      ${(theme.metrics || []).map((key) => {
        const item = ward.metrics?.[key];
        return `<div class="compare-detail-row"><div><span>${escapeHtml(catalog(key).label)}</span><small>${escapeHtml(item?.period || "")}</small></div><div><strong>${escapeHtml(formatDetailValue(key, item?.value))}</strong></div></div>`;
      }).join("")}
    </article>`;
  }

  function ensureThirdCompareSelect() {
    const controls = document.querySelector(".compare-controls");
    const a = document.querySelector("#compare-a");
    const b = document.querySelector("#compare-b");
    if (!controls || !a || !b) return null;
    let c = document.querySelector("#compare-c");
    if (!c) {
      controls.insertAdjacentHTML("beforeend", `<span class="compare-third-separator">VS</span><select id="compare-c" aria-label="比較する3つ目の地域（任意）"><option value="">3つ目は任意</option></select>`);
      c = document.querySelector("#compare-c");
      c?.addEventListener("change", queueCompareSync);
      const title = document.querySelector("#compare-title");
      if (title) title.textContent = "候補を2〜3地域まで絞ったら";
      const note = controls.closest(".compare-section")?.querySelector(".section-note");
      if (note) note.textContent = "候補を最大3地域まで横並びにして、人口・住宅・経済・生活・都市・防災の違いを確認できます。";
    }
    if (c && c.options.length <= 1 && state.areas.length) {
      c.insertAdjacentHTML("beforeend", state.areas.map((area) => `<option value="${escapeHtml(area.area_id)}">${escapeHtml(area.municipality_name)}</option>`).join(""));
    }
    return c;
  }

  function queueCompareSync() {
    if (compareSyncQueued) return;
    compareSyncQueued = true;
    setTimeout(() => {
      compareSyncQueued = false;
      renderThirdCompare();
    }, 0);
  }

  function renderThirdCompare() {
    const c = ensureThirdCompareSelect();
    const cId = c?.value || "";
    const basicTarget = document.querySelector("#compare-grid");
    const detailTarget = document.querySelector("#compare-detail-grid");

    if (basicTarget) {
      const existing = basicTarget.querySelector(".shortlist-third-basic");
      if (!cId) {
        existing?.remove();
        basicTarget.classList.remove("has-third");
      } else if (!existing || existing.dataset.shortlistThird !== cId) {
        existing?.remove();
        const area = state.areas.find((row) => String(row.area_id) === String(cId));
        if (area) basicTarget.insertAdjacentHTML("beforeend", thirdBasicCard(area));
        basicTarget.classList.add("has-third");
      }
    }

    if (detailTarget && state.explore) {
      const active = document.querySelector("#compare-tabs [data-compare-theme].is-active") || document.querySelector("#compare-tabs [data-compare-theme][aria-selected='true']");
      const themeKey = active?.dataset.compareTheme || "people";
      const theme = state.explore.themes?.find((row) => row.key === themeKey);
      const ward = state.explore.wards?.find((row) => String(row.area_id) === String(cId));
      const marker = `${cId}:${themeKey}`;
      const existing = detailTarget.querySelector(".shortlist-third-detail");
      if (!cId || !theme || !ward) {
        existing?.remove();
        detailTarget.classList.remove("has-third");
      } else if (!existing || existing.dataset.shortlistThirdDetail !== marker) {
        existing?.remove();
        detailTarget.insertAdjacentHTML("beforeend", thirdDetailCard(ward, theme));
        detailTarget.classList.add("has-third");
      }
    }
  }

  function applyCompareSelection(ids) {
    const a = document.querySelector("#compare-a");
    const b = document.querySelector("#compare-b");
    const c = ensureThirdCompareSelect();
    if (!a || !b) return false;
    if (!a.options.length || !b.options.length) return false;
    if (ids[0] && [...a.options].some((option) => option.value === ids[0])) a.value = ids[0];
    if (ids[1] && [...b.options].some((option) => option.value === ids[1])) b.value = ids[1];
    if (c) c.value = ids[2] && [...c.options].some((option) => option.value === ids[2]) ? ids[2] : "";
    a.dispatchEvent(new Event("change", { bubbles: true }));
    b.dispatchEvent(new Event("change", { bubbles: true }));
    queueCompareSync();
    return true;
  }

  function compareShortlist() {
    const items = readShortlist();
    if (items.length < 2) return;
    const ids = items.map((item) => item.areaId).slice(0, MAX_ITEMS);
    const url = new URL(location.href);
    url.searchParams.set("compare", ids.join(","));
    url.hash = "compare-title";
    history.replaceState(null, "", url);
    let attempts = 0;
    const apply = () => {
      if (applyCompareSelection(ids)) {
        document.querySelector(".compare-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      if (attempts++ < 30) setTimeout(apply, 100);
    };
    apply();
  }

  function applyCompareFromUrl() {
    const value = new URL(location.href).searchParams.get("compare");
    if (!value) return;
    const ids = value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, MAX_ITEMS);
    if (ids.length < 2) return;
    let attempts = 0;
    const apply = () => {
      if (applyCompareSelection(ids)) return;
      if (attempts++ < 30) setTimeout(apply, 100);
    };
    apply();
  }

  function patchLegacyLabels(root = document) {
    const candidates = root.querySelectorAll?.("option, th, .theme-card small, .compare-detail-row span") || [];
    candidates.forEach((node) => {
      const text = node.textContent?.trim();
      if (text && LABEL_OVERRIDES[text]) node.textContent = LABEL_OVERRIDES[text];
    });
  }

  function setupObservers() {
    const recommendTarget = document.querySelector("#recommend-results");
    if (recommendTarget) {
      new MutationObserver(() => {
        enhanceRecommendationCards();
        renderShortlistPanel();
      }).observe(recommendTarget, { childList: true });
    }

    [document.querySelector("#compare-grid"), document.querySelector("#compare-detail-grid"), document.querySelector("#compare-tabs")]
      .filter(Boolean)
      .forEach((target) => new MutationObserver(() => queueCompareSync()).observe(target, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "aria-selected"] }));

    const exploreRoot = document.querySelector("#discover");
    if (exploreRoot) {
      new MutationObserver(() => patchLegacyLabels(exploreRoot)).observe(exploreRoot, { childList: true, subtree: true });
    }

    ["#compare-a", "#compare-b"].forEach((selector) => {
      document.querySelector(selector)?.addEventListener("change", queueCompareSync);
    });
  }

  async function init() {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "./shortlist.css";
    document.head.appendChild(css);

    try {
      [state.areas, state.explore] = await Promise.all([
        loadJson("./data/areas.json"),
        loadJson("./data/explore/wards.json").catch(() => null),
      ]);
    } catch (error) {
      console.warn("shortlist data unavailable", error);
    }

    ensureShortlistPanel();
    ensureThirdCompareSelect();
    setupObservers();
    enhanceRecommendationCards();
    renderShortlistPanel();
    patchLegacyLabels();
    applyCompareFromUrl();
    queueCompareSync();
  }

  document.addEventListener("townscore:shortlist", () => {
    renderShortlistPanel();
    updateRecommendationButtons();
  });
  document.addEventListener("DOMContentLoaded", init);
})();