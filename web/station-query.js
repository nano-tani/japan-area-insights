(() => {
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyQuery, { once: true });
  } else {
    applyQuery();
  }
  loadRecommendations();
})();
