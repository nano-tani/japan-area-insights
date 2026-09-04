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

if (!document.querySelector('script[data-shortlist-loader]')) {
  const script = document.createElement("script");
  script.src = "./shortlist.js";
  script.async = false;
  script.dataset.shortlistLoader = "true";
  document.head.appendChild(script);
}
