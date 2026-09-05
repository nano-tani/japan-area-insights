(() => {
  const nav = document.querySelector("[data-site-navigation]");
  if (!nav) return;

  const items = [
    { key: "recommend", label: "おすすめから探す", hash: "#recommend" },
    { key: "search", label: "街・駅名から探す", hash: "#name-search" },
    { key: "discover", label: "条件で探す", hash: "#discover" },
  ];

  const context = nav.dataset.navContext || "home";
  const configuredActive = nav.dataset.navActive || "";
  const isHome = context === "home";

  const hrefFor = (item) => {
    if (isHome) return item.hash;
    if (context === "stations" && item.key === "search") return "./stations.html";
    return `./${item.hash}`;
  };

  const links = new Map();
  const fragment = document.createDocumentFragment();

  items.forEach((item) => {
    const link = document.createElement("a");
    link.href = hrefFor(item);
    link.textContent = item.label;
    link.dataset.navKey = item.key;
    links.set(item.key, link);
    fragment.appendChild(link);
  });

  nav.replaceChildren(fragment);

  const keyFromHash = (hash) => {
    const match = items.find((item) => item.hash === hash);
    return match?.key || "recommend";
  };

  const setActive = (key) => {
    links.forEach((link, itemKey) => {
      if (itemKey === key) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  };

  if (isHome) {
    const syncFromLocation = () => setActive(keyFromHash(window.location.hash));

    nav.addEventListener("click", (event) => {
      const link = event.target.closest("a[data-nav-key]");
      if (!link || !nav.contains(link)) return;
      setActive(link.dataset.navKey);
    });

    window.addEventListener("hashchange", syncFromLocation);
    window.addEventListener("pageshow", syncFromLocation);
    syncFromLocation();
  } else if (configuredActive && links.has(configuredActive)) {
    setActive(configuredActive);
  }
})();
