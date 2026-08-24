(() => {
  "use strict";

  const root = document.querySelector(".engineering-center");
  if (!root) return;

  const grid = document.querySelector("#doorGrid");
  const emptyState = document.querySelector("#emptyState");
  const resultCount = document.querySelector("#resultCount");
  const filterCount = document.querySelector("#activeFilterCount");
  const refreshButton = document.querySelector("#refreshNow");
  const refreshTime = document.querySelector("#refreshTime");
  const refreshMessage = document.querySelector("#refreshMessage");
  const tabs = [...root.querySelectorAll("[data-engineering-tab]")];
  const panels = [...root.querySelectorAll("[data-engineering-panel]")];
  const mapFrame = root.querySelector("[data-map-frame]");
  const controlIds = ["q", "status", "density", "incident", "maint", "sort"];
  let refreshPending = false;

  function activateTab(tab) {
    const target = tab.dataset.engineeringTab;
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => { panel.hidden = panel.dataset.engineeringPanel !== target; });
    if (target === "map" && mapFrame && !mapFrame.src) mapFrame.src = mapFrame.dataset.src;
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? -1 : 1) + tabs.length) % tabs.length;
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    });
  });

  function cards() {
    return [...grid.querySelectorAll(".engineering-card")];
  }

  function activeFilters() {
    return ["q", "status", "density", "incident", "maint"].filter((id) => {
      const value = document.querySelector(`#${id}`).value.trim();
      return id === "q" ? Boolean(value) : value !== "all";
    }).length;
  }

  function applyFilters() {
    const query = document.querySelector("#q").value.trim().toLowerCase();
    const status = document.querySelector("#status").value;
    const density = document.querySelector("#density").value;
    const incident = document.querySelector("#incident").value;
    const maintenance = document.querySelector("#maint").value;
    const sort = document.querySelector("#sort").value;
    const allCards = cards();
    let visible = 0;

    allCards.forEach((card) => {
      const matches = (!query || card.dataset.number.toLowerCase().includes(query))
        && (status === "all" || card.dataset.status === status)
        && (density === "all" || card.dataset.density === density)
        && (incident === "all" || (incident === "yes") === (Number(card.dataset.incidents) > 0))
        && (maintenance === "all" || (maintenance === "yes") === (Number(card.dataset.maintenance) > 0));
      card.hidden = !matches;
      if (matches) visible += 1;
    });

    const key = sort === "order" ? "order" : sort;
    allCards.sort((a, b) => sort === "order"
      ? Number(a.dataset[key]) - Number(b.dataset[key])
      : Number(b.dataset[key]) - Number(a.dataset[key]));
    allCards.forEach((card) => grid.appendChild(card));

    resultCount.textContent = `عرض ${visible} من ${allCards.length}`;
    emptyState.hidden = visible !== 0;
    grid.hidden = visible === 0;
    const count = activeFilters();
    filterCount.hidden = count === 0;
    filterCount.textContent = `${count} ${count === 1 ? "فلتر مفعّل" : "فلاتر مفعّلة"}`;
  }

  function resetFilters() {
    document.querySelector("#q").value = "";
    ["status", "density", "incident", "maint"].forEach((id) => { document.querySelector(`#${id}`).value = "all"; });
    document.querySelector("#sort").value = "order";
    applyFilters();
    document.querySelector("#q").focus();
  }

  function bindInteractions() {
    document.querySelectorAll(".engineering-card__details").forEach((button) => {
      button.addEventListener("click", () => {
        const drawer = document.querySelector(`#${button.getAttribute("aria-controls")}`);
        drawer.hidden = !drawer.hidden;
        button.setAttribute("aria-expanded", String(!drawer.hidden));
        button.textContent = drawer.hidden ? "عرض التفاصيل" : "إخفاء التفاصيل";
      });
    });

  }

  function showRefreshError(message = "تعذر تحديث البيانات") {
    refreshMessage.hidden = false;
    refreshMessage.textContent = `⚠ ${message} — يتم عرض آخر بيانات متاحة`;
  }

  function updateAlertIndicators(card, incidentCount, maintenanceCount) {
    let alerts = card.querySelector(".engineering-card__alerts");
    if (!incidentCount && !maintenanceCount) { alerts?.remove(); return; }
    if (!alerts) {
      alerts = document.createElement("div");
      alerts.className = "engineering-card__alerts";
      card.querySelector(".engineering-card__header").after(alerts);
    }
    alerts.replaceChildren();
    if (incidentCount) alerts.insertAdjacentHTML("beforeend", `<span class="engineering-card__alert engineering-card__alert--incident">بلاغ مفتوح · ${incidentCount}</span>`);
    if (maintenanceCount) alerts.insertAdjacentHTML("beforeend", `<span class="engineering-card__alert engineering-card__alert--maintenance">صيانة نشطة · ${maintenanceCount}</span>`);
  }

  async function refreshCards({ manual = false } = {}) {
    if (refreshPending || (document.hidden && !manual)) return;
    refreshPending = true;
    refreshButton.classList.add("is-loading");
    refreshButton.disabled = true;
    refreshMessage.hidden = true;
    try {
      const response = await fetch(root.dataset.refreshUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!response.ok) throw new Error("refresh failed");
      const payload = await response.json();
      payload.doors.forEach((item) => {
        const card = grid.querySelector(`[data-door-id="${item.id}"]`);
        if (!card) return;
        card.classList.remove("engineering-card--open", "engineering-card--closed", "engineering-card--maintenance", "engineering-card--secured");
        card.classList.add(`engineering-card--${item.status}`);
        card.dataset.status = item.status;
        card.dataset.employees = item.employee_count;
        card.dataset.incidents = item.open_incident_count;
        card.dataset.maintenance = item.active_maintenance_count;
        card.querySelector("[data-metric='status']").lastChild.textContent = item.status_label;
        card.querySelector("[data-metric='employees']").textContent = item.employee_count;
        card.querySelector("[data-metric='incidents']").textContent = item.open_incident_count;
        card.querySelector("[data-metric='maintenance']").textContent = item.active_maintenance_count;
        card.querySelector("[data-detail='status']").textContent = item.status_label;
        card.querySelector("[data-detail='status-copy']").textContent = item.status_label;
        card.querySelector("[data-detail='employees']").textContent = item.employee_count;
        card.querySelector("[data-detail='incidents']").textContent = item.open_incident_count;
        card.querySelector("[data-detail='maintenance']").textContent = item.active_maintenance_count;
        card.querySelector("[data-metric='activity']").textContent = item.last_activity ? new Date(item.last_activity).toLocaleString("ar-SA", { day: "numeric", month: "long", hour: "numeric", minute: "2-digit" }) : "لا يوجد نشاط مسجل";
        updateAlertIndicators(card, item.open_incident_count, item.active_maintenance_count);
      });
      Object.entries(payload.summary).forEach(([key, value]) => {
        document.querySelector(`[data-summary="${key}"]`)?.replaceChildren(String(value));
      });
      applyFilters();
      root.dispatchEvent(new CustomEvent("engineering:center-refreshed", { detail: payload }));
      refreshTime.textContent = new Date().toLocaleTimeString("ar-SA", { hour: "numeric", minute: "2-digit" });
    } catch (error) {
      showRefreshError();
    } finally {
      refreshPending = false;
      refreshButton.classList.remove("is-loading");
      refreshButton.disabled = false;
    }
  }

  controlIds.forEach((id) => document.querySelector(`#${id}`).addEventListener(id === "q" ? "input" : "change", applyFilters));
  document.querySelector("#resetFilters").addEventListener("click", resetFilters);
  document.querySelector("[data-reset-filters]").addEventListener("click", resetFilters);
  refreshButton.addEventListener("click", () => refreshCards({ manual: true }));
  bindInteractions();
  applyFilters();
  window.setInterval(refreshCards, 45000);
})();
