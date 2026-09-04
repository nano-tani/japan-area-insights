(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const query = new URLSearchParams(location.search).get("q") || "";
    const input = document.querySelector("#station-search");
    if (!input || !query.trim()) return;
    input.value = query;
    // stations.js reads the current input value when its data load finishes.
    // Keep the viewport at the search area so the immediate matches are seen first.
  });
})();
