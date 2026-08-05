(function () {
  "use strict";

  const normalize = (value) => String(value || "")
    .normalize("NFKD")
    .replace(/[\u064B-\u065F\u0670]/g, "")
    .replace(/[أإآٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .trim()
    .toLowerCase();
  const search = document.getElementById("reportsSearch");
  const clearSearch = document.querySelector("[data-clear-search]");
  const cards = [...document.querySelectorAll(".xc-report-card")];
  const filterButtons = [...document.querySelectorAll(".xc-filter[data-format]")];
  const favoritesFilter = document.querySelector("[data-favorites-only]");
  const visibleCountNode = document.querySelector("[data-visible-count]");
  const emptyState = document.getElementById("filteredEmptyState");
  const storageKey = "abwab.export-center.preferences.v1";
  let activeFormat = "all";
  let favoritesOnly = false;

  function loadPreferences() {
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) || "{}");
      return {
        favorites: Array.isArray(saved.favorites) ? saved.favorites : [],
        view: saved.view === "list" ? "list" : "grid",
      };
    } catch (error) {
      return { favorites: [], view: "grid" };
    }
  }

  const preferences = loadPreferences();
  const favorites = new Set(preferences.favorites);

  function savePreferences(view) {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({
        favorites: [...favorites],
        view: view || (document.getElementById("reportsGrid")?.classList.contains("list-view") ? "list" : "grid"),
      }));
    } catch (error) {
      // التصفح الخاص أو سياسات المؤسسة قد تمنع التخزين المحلي؛ لا نعطل الصفحة.
    }
  }

  function syncFavoriteButton(button) {
    const key = button.dataset.favoriteKey || "";
    const active = favorites.has(key);
    const card = button.closest(".xc-report-card");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.title = active ? "إزالة من المفضلة" : "إضافة إلى المفضلة";
    button.setAttribute("aria-label", `${active ? "إزالة" : "إضافة"} ${card?.querySelector("h3")?.textContent?.trim() || "التقرير"} ${active ? "من" : "إلى"} المفضلة`);
    card?.classList.toggle("is-favorite", active);
  }

  function applyFilters() {
    const term = normalize(search && search.value);
    let visibleCount = 0;
    cards.forEach((card) => {
      const formats = normalize(card.dataset.formats).split(/\s+/);
      const reportKey = card.dataset.reportKey || "";
      const visible = (!term || normalize(card.dataset.search).includes(term))
        && (activeFormat === "all" || formats.includes(activeFormat))
        && (!favoritesOnly || favorites.has(reportKey));
      card.hidden = !visible;
      if (visible) visibleCount += 1;
    });
    if (emptyState) emptyState.hidden = visibleCount > 0;
    if (visibleCountNode) visibleCountNode.textContent = String(visibleCount);
    if (clearSearch) clearSearch.hidden = !term;
  }

  if (search) search.addEventListener("input", applyFilters);
  if (clearSearch) clearSearch.addEventListener("click", () => {
    if (search) {
      search.value = "";
      search.focus();
    }
    applyFilters();
  });
  filterButtons.forEach((button) => button.addEventListener("click", () => {
    filterButtons.forEach((item) => item.classList.remove("active"));
    filterButtons.forEach((item) => item.setAttribute("aria-pressed", "false"));
    button.classList.add("active");
    button.setAttribute("aria-pressed", "true");
    activeFormat = button.dataset.format || "all";
    applyFilters();
  }));

  document.querySelectorAll("[data-favorite-key]").forEach((button) => {
    syncFavoriteButton(button);
    button.addEventListener("click", () => {
      const key = button.dataset.favoriteKey || "";
      if (favorites.has(key)) favorites.delete(key);
      else favorites.add(key);
      syncFavoriteButton(button);
      savePreferences();
      applyFilters();
    });
  });

  if (favoritesFilter) favoritesFilter.addEventListener("click", () => {
    favoritesOnly = !favoritesOnly;
    favoritesFilter.classList.toggle("active", favoritesOnly);
    favoritesFilter.setAttribute("aria-pressed", String(favoritesOnly));
    applyFilters();
  });

  const grid = document.getElementById("reportsGrid");
  const viewButtons = [...document.querySelectorAll("[data-view]")];
  function setView(view, persist) {
    viewButtons.forEach((item) => {
      const active = item.dataset.view === view;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    if (grid) grid.classList.toggle("list-view", view === "list");
    if (persist) savePreferences(view);
  }
  viewButtons.forEach((button) => button.addEventListener("click", () => setView(button.dataset.view || "grid", true)));
  setView(preferences.view, false);

  const modal = document.getElementById("exportModal");
  const title = document.getElementById("exportModalTitle");
  const selectedReport = document.getElementById("selectedReportTitle");
  const filtersLink = document.getElementById("modalFiltersLink");
  const formatLinks = [...document.querySelectorAll("[data-export-format]")];
  let modalTrigger = null;

  function buildUrl(template, reportKey, format) {
    const reportUrl = template.replace("__REPORT_KEY__", encodeURIComponent(reportKey));
    return format ? reportUrl.replace("__FORMAT__", format) : reportUrl;
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    modalTrigger?.focus();
  }

  document.querySelectorAll(".open-export-modal").forEach((button) => button.addEventListener("click", () => {
    if (!modal || !window.EXPORT_CENTER_URLS) return;
    modalTrigger = button;
    const reportKey = button.dataset.reportKey || "";
    const reportTitle = button.dataset.reportTitle || "التقرير";
    const supported = normalize(button.dataset.formats).split(/\s+/);
    title.textContent = `تصدير ${reportTitle}`;
    selectedReport.textContent = reportTitle;
    formatLinks.forEach((link) => {
      const format = link.dataset.exportFormat;
      const enabled = supported.includes(format);
      link.hidden = !enabled;
      if (enabled) link.href = buildUrl(window.EXPORT_CENTER_URLS.exportTemplate, reportKey, format);
      else link.removeAttribute("href");
    });
    filtersLink.href = buildUrl(window.EXPORT_CENTER_URLS.filtersTemplate, reportKey);
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    modal.querySelector("[data-export-format]:not([hidden]), [data-close-modal]")?.focus();
  }));

  document.querySelectorAll("[data-close-modal]").forEach((button) => button.addEventListener("click", closeModal));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  applyFilters();
}());
