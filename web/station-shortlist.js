(() => {
  const STORAGE_KEY = "town-score-station-shortlist-v1";
  const MAX_ITEMS = 3;

  function normalizeItem(item) {
    if (!item) return null;
    const code = String(item.station_code || item.code || "").trim();
    const name = String(item.name || code).trim();
    if (!/^\d+$/.test(code) || !name) return null;
    return {
      code,
      name,
      ward: String(item.primary_ward_name || item.ward || "").trim(),
    };
  }

  function read() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed.map(normalizeItem).filter(Boolean).slice(0, MAX_ITEMS);
    } catch (_) {
      return [];
    }
  }

  function write(items) {
    const normalized = (Array.isArray(items) ? items : []).map(normalizeItem).filter(Boolean).slice(0, MAX_ITEMS);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    } catch (_) {
      return read();
    }
    document.dispatchEvent(new CustomEvent("townscore:station-shortlist", { detail: normalized }));
    return normalized;
  }

  function has(code) {
    return read().some((item) => item.code === String(code));
  }

  function toggle(station) {
    const item = normalizeItem(station);
    if (!item) return { items: read(), changed: false, reason: "invalid" };
    const items = read();
    const index = items.findIndex((row) => row.code === item.code);
    if (index >= 0) {
      items.splice(index, 1);
      return { items: write(items), changed: true, saved: false };
    }
    if (items.length >= MAX_ITEMS) return { items, changed: false, saved: false, reason: "full" };
    items.push(item);
    return { items: write(items), changed: true, saved: true };
  }

  function remove(code) {
    return write(read().filter((item) => item.code !== String(code)));
  }

  function clear() {
    return write([]);
  }

  function compareUrl(basePath = "./station-compare.html", items = read()) {
    const codes = items.map((item) => item.code).filter(Boolean).slice(0, MAX_ITEMS);
    return `${basePath}?codes=${encodeURIComponent(codes.join(","))}`;
  }

  window.StationShortlist = Object.freeze({
    STORAGE_KEY,
    MAX_ITEMS,
    read,
    write,
    has,
    toggle,
    remove,
    clear,
    compareUrl,
    normalizeItem,
  });
})();
