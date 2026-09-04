(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const query = new URLSearchParams(location.search).get("q") || "";
    const input = document.querySelector("#station-search");
    if (!input || !query.trim()) return;
    input.value = query;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const ranking = document.querySelector("#station-ranking-title");
    ranking?.scrollIntoView({ block: "start" });
  });
})();
