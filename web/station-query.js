(() => {
  function installStaticJsonRequestCache() {
    if (window.__townScoreStaticJsonCacheInstalled) return;
    const nativeFetch = window.fetch.bind(window);
    const responses = new Map();

    window.fetch = (input, init = {}) => {
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      let url;
      try {
        url = new URL(typeof input === "string" ? input : input.url, window.location.href);
      } catch (_) {
        return nativeFetch(input, init);
      }

      const isStaticJson = method === "GET"
        && url.origin === window.location.origin
        && /\/data\/.+\.json$/.test(url.pathname);
      if (!isStaticJson) return nativeFetch(input, init);

      const key = url.href;
      if (!responses.has(key)) {
        const request = nativeFetch(input, init)
          .then((response) => {
            if (!response.ok) responses.delete(key);
            return response;
          })
          .catch((error) => {
            responses.delete(key);
            throw error;
          });
        responses.set(key, request);
      }
      return responses.get(key).then((response) => response.clone());
    };
    window.__townScoreStaticJsonCacheInstalled = true;
  }

  function installStaticStationNavigation() {
    window.openStationDetail = (stationCode) => {
      const code = String(stationCode || "").trim();
      if (!/^\d+$/.test(code)) return;
      window.location.href = `./station/${encodeURIComponent(code)}/`;
    };
  }

  function applyQuery() {
    const query = new URLSearchParams(location.search).get("q") || "";
    const input = document.querySelector("#station-search");
    if (!input || !query.trim()) return;
    input.value = query;
    // stations.js reads the current input value when its data load finishes.
    // Keep the viewport at the search area so the immediate matches are seen first.
  }

  function loadRecommendations() {
    if (document.querySelector('script[data-station-recommend-loader]')) return;
    const script = document.createElement("script");
    script.src = "./station-recommend.js";
    script.async = false;
    script.dataset.stationRecommendLoader = "true";
    document.head.appendChild(script);
  }

  installStaticJsonRequestCache();
  installStaticStationNavigation();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyQuery, { once: true });
  } else {
    applyQuery();
  }
  loadRecommendations();
})();
