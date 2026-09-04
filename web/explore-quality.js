(() => {
  const LABEL_OVERRIDES = {
    "household.single_household_share": "1人世帯比率",
    "people.child_share": "子ども人口比率",
    "people.elderly_share": "高齢者人口比率",
    "demographics.natural_change": "出生死亡差",
  };
  let data = null;
  let applying = false;

  async function loadData() {
    const response = await fetch("./data/explore/wards.json", { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  }

  function metricAvailable(key) {
    return Boolean(data?.wards?.some((ward) => {
      const value = ward.metrics?.[key]?.value;
      return value !== null && value !== undefined && !Number.isNaN(Number(value));
    }));
  }

  function patchLabels(root = document) {
    root.querySelectorAll("option, th, .theme-card small, .compare-detail-row span").forEach((node) => {
      const text = node.textContent?.trim();
      if (text && LABEL_OVERRIDES[text] && node.textContent !== LABEL_OVERRIDES[text]) {
        node.textContent = LABEL_OVERRIDES[text];
      }
    });
  }

  function patchControls() {
    [document.querySelector("#explore-sort"), document.querySelector("#filter-metric")].filter(Boolean).forEach((select) => {
      [...select.options].forEach((option) => {
        option.disabled = !metricAvailable(option.value);
        if (option.disabled) option.hidden = true;
      });
      if (select.selectedOptions[0]?.disabled) {
        const first = [...select.options].find((option) => !option.disabled);
        if (first) {
          select.value = first.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    });
  }

  function patchTable() {
    const themeKey = document.querySelector("#explore-theme")?.value;
    const theme = data?.themes?.find((item) => item.key === themeKey);
    if (!theme) return;
    (theme.metrics || []).forEach((key, index) => {
      const visible = metricAvailable(key);
      const nth = index + 2;
      document.querySelectorAll(`#explore-head th:nth-child(${nth}), #explore-body td:nth-child(${nth})`).forEach((cell) => {
        cell.style.display = visible ? "" : "none";
      });
    });
  }

  function patchCompareRows() {
    document.querySelectorAll(".compare-detail-row").forEach((row) => {
      const value = row.querySelector("div:last-child strong")?.textContent?.trim();
      const label = row.querySelector("div:first-child span")?.textContent?.trim();
      if (value === "—" && Object.values(LABEL_OVERRIDES).includes(label)) row.hidden = true;
    });
  }

  function apply() {
    if (!data || applying) return;
    applying = true;
    try {
      patchLabels();
      patchControls();
      patchTable();
      patchCompareRows();
    } finally {
      applying = false;
    }
  }

  async function init() {
    data = await loadData().catch(() => null);
    if (!data) return;
    apply();
    const roots = [document.querySelector("#discover"), document.querySelector("#compare-detail-grid"), document.querySelector("#theme-grid")].filter(Boolean);
    roots.forEach((root) => new MutationObserver(() => queueMicrotask(apply)).observe(root, { childList: true, subtree: true }));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();