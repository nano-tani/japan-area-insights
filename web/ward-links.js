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

installStaticJsonRequestCache();

function syncPrimaryNavCurrent() {
  const links = [...document.querySelectorAll('.site-nav a[href^="#"]')];
  if (!links.length) return;

  const currentHash = window.location.hash;
  const activeHash = links.some((link) => link.getAttribute("href") === currentHash)
    ? currentHash
    : "#recommend";

  links.forEach((link) => {
    if (link.getAttribute("href") === activeHash) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

syncPrimaryNavCurrent();
window.addEventListener("hashchange", syncPrimaryNavCurrent);

function openWardPage(areaId) {
  if (!areaId) return;
  window.location.href = `./ward.html?id=${encodeURIComponent(areaId)}`;
}

document.addEventListener("click", (event) => {
  const target = event.target.closest(".insight-card, #ranking-body tr, .area-card");
  if (!target?.dataset?.areaId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  openWardPage(target.dataset.areaId);
}, true);

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const target = event.target.closest(".insight-card, .area-card");
  if (!target?.dataset?.areaId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  openWardPage(target.dataset.areaId);
}, true);

function loadEnhancement(src, marker) {
  if (document.querySelector(`script[data-enhancement="${marker}"]`)) return;
  const script = document.createElement("script");
  script.src = src;
  script.async = false;
  script.dataset.enhancement = marker;
  document.head.appendChild(script);
}

loadEnhancement("./shortlist.js", "shortlist");
loadEnhancement("./explore-quality.js", "explore-quality");
