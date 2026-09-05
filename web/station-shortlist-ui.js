(() => {
  const store = () => window.StationShortlist;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'\"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));
  }

  function stationFromButton(button) {
    return {
      station_code: button.dataset.stationSave,
      name: button.dataset.stationName || button.dataset.stationSave,
      primary_ward_name: button.dataset.stationWard || "",
    };
  }

  function ensurePanel() {
    let panel = document.querySelector("#station-shortlist-panel");
    if (panel) return panel;
    const hero = document.querySelector(".station-hero");
    if (!hero) return null;
    panel = document.createElement("section");
    panel.id = "station-shortlist-panel";
    panel.className = "station-shortlist-panel";
    panel.setAttribute("aria-live", "polite");
    hero.insertAdjacentElement("afterend", panel);
    return panel;
  }

  function renderPanel() {
    const shortlist = store();
    const panel = ensurePanel();
    if (!shortlist || !panel) return;
    const items = shortlist.read();
    panel.innerHTML = `
      <div class="station-shortlist-copy">
        <span>CANDIDATES</span>
        <strong>気になる駅 ${items.length} / ${shortlist.MAX_ITEMS}</strong>
        <small>この端末に保存。2駅以上で比較できます。</small>
      </div>
      <div class="station-shortlist-chips">
        ${items.length ? items.map((item) => `
          <button type="button" data-station-shortlist-remove="${escapeHtml(item.code)}" aria-label="${escapeHtml(item.name)}駅を候補から外す">
            ${escapeHtml(item.name)}駅 <span>×</span>
          </button>`).join("") : '<span class="station-shortlist-empty">検索結果やおすすめから「候補に保存」を押してください。</span>'}
      </div>
      <div class="station-shortlist-actions">
        ${items.length >= 2
          ? `<a href="${shortlist.compareUrl("./station-compare.html", items)}">${items.length}駅を比較する</a>`
          : '<span class="station-shortlist-wait">あと1駅保存すると比較できます</span>'}
        ${items.length ? '<button type="button" data-station-shortlist-clear>すべて外す</button>' : ""}
      </div>`;

    panel.querySelectorAll("[data-station-shortlist-remove]").forEach((button) => {
      button.addEventListener("click", () => shortlist.remove(button.dataset.stationShortlistRemove));
    });
    panel.querySelector("[data-station-shortlist-clear]")?.addEventListener("click", () => shortlist.clear());
  }

  function refreshButtons() {
    const shortlist = store();
    if (!shortlist) return;
    const items = shortlist.read();
    const savedCodes = new Set(items.map((item) => item.code));
    const full = items.length >= shortlist.MAX_ITEMS;
    document.querySelectorAll("[data-station-save]").forEach((button) => {
      const code = String(button.dataset.stationSave || "");
      const saved = savedCodes.has(code);
      button.classList.toggle("is-saved", saved);
      button.disabled = !saved && full;
      button.setAttribute("aria-pressed", String(saved));
      button.textContent = saved ? "保存済み" : full ? "候補は3駅まで" : "候補に保存";
    });
  }

  function refresh() {
    renderPanel();
    refreshButtons();
  }

  function bindDocumentActions() {
    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-station-save]");
      if (!button) return;
      event.preventDefault();
      event.stopPropagation();
      const shortlist = store();
      if (!shortlist) return;
      shortlist.toggle(stationFromButton(button));
    });
  }

  function init() {
    if (!store()) return;
    bindDocumentActions();
    refresh();
    document.addEventListener("townscore:station-shortlist", refresh);
    document.addEventListener("townscore:station-cards-rendered", refreshButtons);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
