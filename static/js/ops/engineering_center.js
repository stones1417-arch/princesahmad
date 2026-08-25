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
  const followupBackdrop = root.querySelector("[data-followup-backdrop]");
  const controlIds = ["q", "status", "coverage", "incident", "maint", "sort"];
  let refreshPending = false;
  let activeFollowupButton = null;
  let activeFollowupDrawer = null;
  let followupController = null;
  let followupRequestId = 0;

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
    return ["q", "status", "coverage", "incident", "maint"].filter((id) => {
      const value = document.querySelector(`#${id}`).value.trim();
      return id === "q" ? Boolean(value) : value !== "all";
    }).length;
  }

  function applyFilters() {
    const query = document.querySelector("#q").value.trim().toLowerCase();
    const status = document.querySelector("#status").value;
    const coverage = document.querySelector("#coverage").value;
    const incident = document.querySelector("#incident").value;
    const maintenance = document.querySelector("#maint").value;
    const sort = document.querySelector("#sort").value;
    const allCards = cards();
    let visible = 0;

    allCards.forEach((card) => {
      const matches = (!query || card.dataset.number.toLowerCase().includes(query))
        && (status === "all" || card.dataset.status === status)
        && (coverage === "all" || card.dataset.coverage === coverage)
        && (incident === "all" || (incident === "yes") === (Number(card.dataset.incidents) > 0))
        && (maintenance === "all" || (maintenance === "yes") === (Number(card.dataset.maintenance) > 0));
      card.hidden = !matches;
      if (matches) visible += 1;
    });

    allCards.sort((a, b) => {
      if (sort === "order") return Number(a.dataset.order) - Number(b.dataset.order);
      if (sort === "coverage-low") return Number(a.dataset.coveragePercent) - Number(b.dataset.coveragePercent);
      if (sort === "coverage-high") return Number(b.dataset.coveragePercent) - Number(a.dataset.coveragePercent);
      return Number(b.dataset[sort]) - Number(a.dataset[sort]);
    });
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
    ["status", "coverage", "incident", "maint"].forEach((id) => { document.querySelector(`#${id}`).value = "all"; });
    document.querySelector("#sort").value = "order";
    applyFilters();
    document.querySelector("#q").focus();
  }

  const escapeHtml = (value) => { const node = document.createElement("div"); node.textContent = String(value ?? ""); return node.innerHTML; };
  const waitingLabel = (seconds) => seconds < 3600 ? `منذ ${Math.max(1, Math.floor(seconds / 60))} دقيقة` : `منذ ${Math.floor(seconds / 3600)} ساعة و${Math.floor((seconds % 3600) / 60)} دقيقة`;

  function incidentMarkup(item) {
    const maintenance = item.maintenance ? `<section class="engineering-followup__maintenance"><strong>طلب الصيانة المرتبط: ${escapeHtml(item.maintenance.number)}</strong><span>${escapeHtml(item.maintenance.status_label)}</span>${item.maintenance.technician ? `<small>الفني: ${escapeHtml(item.maintenance.technician)}</small>` : ""}${item.maintenance.planned_start ? `<small>الوقت المخطط: ${escapeHtml(item.maintenance.planned_start)} — ${escapeHtml(item.maintenance.planned_end)}</small>` : ""}</section>` : "";
    const update = item.last_update ? `<section class="engineering-followup__update"><strong>آخر تحديث من مركز الوردية</strong><p>${escapeHtml(item.last_update.note)}</p><small>من: ${escapeHtml(item.last_update.actor)} · ${escapeHtml(item.last_update.created_at)}</small></section>` : "";
    const escalation = item.escalation_note ? `<p class="engineering-followup__escalation"><strong>سبب التصعيد:</strong> ${escapeHtml(item.escalation_note)}<small>${escapeHtml(item.escalated_by)} · ${escapeHtml(item.escalated_at)}</small></p>` : "";
    const events = item.events.map((event) => `<li class="is-${event.state}"><i aria-hidden="true"></i><div><strong>${escapeHtml(event.label)}</strong><small>${escapeHtml(event.actor)} · ${escapeHtml(event.created_at)}</small>${event.note ? `<p>${escapeHtml(event.note)}</p>` : ""}</div></li>`).join("");
    return `<article class="engineering-followup" data-followup-incident="${item.id}" data-followup-filter="${item.is_closed ? "closed" : "open"} ${item.status} ${item.escalation !== "غير مصعّد" ? "escalated" : ""} ${item.maintenance ? "maintenance" : ""}"><header><div><small>${escapeHtml(item.number)}</small><h5>${escapeHtml(item.type)}</h5></div><span class="stage-${item.stage}">${escapeHtml(item.stage_label)}</span></header><dl><div><dt>الأولوية</dt><dd>${escapeHtml(item.priority_label)}</dd></div><div><dt>الحالة</dt><dd>${escapeHtml(item.status_label)}</dd></div><div><dt>وقت الإنشاء</dt><dd>${escapeHtml(item.created_at)}</dd></div><div><dt>مدة الانتظار</dt><dd>${waitingLabel(item.waiting_seconds)}</dd></div><div><dt>المسؤول التنفيذي</dt><dd>${escapeHtml(item.assignee)}</dd></div><div><dt>مستوى التصعيد</dt><dd>${escapeHtml(item.escalation)}</dd></div></dl>${escalation}${update}${maintenance}${item.closed_at ? `<p class="engineering-followup__closed">✓ تم إغلاق البلاغ · ${escapeHtml(item.closed_by)} · ${escapeHtml(item.closed_at)}</p>` : ""}<details><summary>عرض المسار الكامل</summary><ol class="engineering-followup__timeline">${events || "<li><div><strong>لا توجد أحداث مسار مسجلة.</strong></div></li>"}</ol></details></article>`;
  }

  function renderFollowup(drawer, payload) {
    const body = drawer.querySelector("[data-followup-body]");
    const createAction = root.dataset.canCreateIncident === "true" ? `<a href="/ops/incidents/?engineering_door=${encodeURIComponent(payload.door.id)}&create=1">إنشاء بلاغ تشغيلي</a>` : "";
    body.innerHTML = `<section class="engineering-followup__summary"><article><small>البلاغات المفتوحة</small><strong>${payload.summary.open}</strong></article><article><small>قيد المعالجة</small><strong>${payload.summary.processing}</strong></article><article><small>المصعّدة</small><strong>${payload.summary.escalated}</strong></article><article><small>مرتبطة بالصيانة</small><strong>${payload.summary.maintenance}</strong></article><article><small>المغلقة اليوم</small><strong>${payload.summary.closed_today}</strong></article></section><nav class="engineering-followup__filters" aria-label="تصفية بلاغات الباب"><button data-followup-filter-value="all" aria-pressed="true">الكل</button><button data-followup-filter-value="open">مفتوحة</button><button data-followup-filter-value="in_progress">قيد المعالجة</button><button data-followup-filter-value="escalated">مصعّدة</button><button data-followup-filter-value="maintenance">صيانة</button><button data-followup-filter-value="closed">مغلقة</button></nav><div class="engineering-followup__list">${payload.incidents.length ? payload.incidents.map(incidentMarkup).join("") : `<div class="engineering-followup__empty"><strong>لا توجد بلاغات مسجلة على هذا الباب.</strong>${createAction}</div>`}</div>`;
    body.querySelectorAll("[data-followup-filter-value]").forEach((button) => button.addEventListener("click", () => {
      const value = button.dataset.followupFilterValue;
      body.querySelectorAll("[data-followup-filter-value]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      body.querySelectorAll("[data-followup-incident]").forEach((card) => { card.hidden = value !== "all" && !card.dataset.followupFilter.split(" ").includes(value); });
    }));
  }

  const followupLoadingMarkup = '<p role="status">جارٍ تحميل مسار البلاغات…</p>';

  function closeIncidentFollowupDrawer({ restoreFocus = true } = {}) {
    const button = activeFollowupButton;
    const drawer = activeFollowupDrawer;
    followupRequestId += 1;
    followupController?.abort();
    followupController = null;
    if (drawer) {
      drawer.hidden = true;
      drawer.setAttribute("aria-hidden", "true");
      drawer.removeAttribute("data-open");
      drawer.querySelector("[data-followup-body]").innerHTML = followupLoadingMarkup;
    }
    if (button) {
      button.setAttribute("aria-expanded", "false");
      button.textContent = "متابعة البلاغات";
    }
    followupBackdrop.hidden = true;
    followupBackdrop.setAttribute("aria-hidden", "true");
    document.body.classList.remove("engineering-followup-open");
    activeFollowupButton = null;
    activeFollowupDrawer = null;
    if (restoreFocus) button?.focus();
  }

  function showFollowupError(drawer) {
    if (drawer !== activeFollowupDrawer || drawer.hidden) return;
    drawer.querySelector("[data-followup-body]").innerHTML = '<div class="engineering-followup__empty" role="alert"><strong>تعذر تحميل بيانات البلاغات.</strong><div><button type="button" data-followup-retry>إعادة المحاولة</button><button type="button" data-followup-error-close>إغلاق</button></div></div>';
  }

  async function loadFollowup(button, { preserve = false } = {}) {
    const drawer = document.querySelector(`#${button.getAttribute("aria-controls")}`);
    if (drawer !== activeFollowupDrawer || button !== activeFollowupButton || drawer.hidden) return;
    const expanded = preserve ? [...drawer.querySelectorAll("details[open]")].map((item) => item.closest("[data-followup-incident]")?.dataset.followupIncident) : [];
    followupController?.abort();
    const controller = new AbortController();
    const requestId = ++followupRequestId;
    followupController = controller;
    if (!preserve) drawer.querySelector("[data-followup-body]").innerHTML = followupLoadingMarkup;
    try {
      const response = await fetch(button.dataset.followupUrl, { headers: { "X-Requested-With": "XMLHttpRequest" }, signal: controller.signal });
      if (!response.ok) throw new Error("followup fetch failed");
      const payload = await response.json();
      if (requestId !== followupRequestId || drawer !== activeFollowupDrawer || drawer.hidden) return;
      renderFollowup(drawer, payload);
      expanded.forEach((id) => drawer.querySelector(`[data-followup-incident="${id}"] details`)?.setAttribute("open", ""));
    } catch (error) {
      if (error.name !== "AbortError") showFollowupError(drawer);
    } finally {
      if (followupController === controller) followupController = null;
    }
  }

  function bindInteractions() {
    document.querySelectorAll("[data-incident-followup]").forEach((button) => button.addEventListener("click", async () => {
      const drawer = document.querySelector(`#${button.getAttribute("aria-controls")}`);
      if (button === activeFollowupButton && !drawer.hidden) { closeIncidentFollowupDrawer(); return; }
      if (activeFollowupDrawer) closeIncidentFollowupDrawer({ restoreFocus: false });
      activeFollowupButton = button;
      activeFollowupDrawer = drawer;
      drawer.hidden = false;
      drawer.setAttribute("aria-hidden", "false");
      drawer.dataset.open = "true";
      button.setAttribute("aria-expanded", "true");
      button.textContent = "إخفاء متابعة البلاغات";
      followupBackdrop.hidden = false;
      followupBackdrop.setAttribute("aria-hidden", "false");
      document.body.classList.add("engineering-followup-open");
      drawer.querySelector("[data-close-followup]").focus();
      await loadFollowup(button);
    }));
    root.addEventListener("click", (event) => {
      if (event.target.closest("[data-close-followup], [data-followup-error-close]")) closeIncidentFollowupDrawer();
      if (event.target.closest("[data-followup-retry]") && activeFollowupButton) loadFollowup(activeFollowupButton);
      if (event.target === followupBackdrop) closeIncidentFollowupDrawer();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && activeFollowupDrawer) closeIncidentFollowupDrawer();
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
        card.dataset.coverage = item.staff_coverage_level;
        card.dataset.coveragePercent = item.staff_coverage_percent ?? -1;
        card.querySelector("[data-metric='status']").lastChild.textContent = item.status_label;
        card.querySelector("[data-metric='employees']").textContent = item.employee_count;
        card.querySelector("[data-metric='incidents']").textContent = item.open_incident_count;
        card.querySelector("[data-metric='incidents-today']").textContent = item.today_incident_count;
        card.querySelector("[data-metric='maintenance']").textContent = item.active_maintenance_count;
        card.querySelector("[data-metric='coverage']").textContent = item.target_staff_count ? `${item.staff_coverage_percent}%` : "غير مهيأة";
        card.querySelector("[data-metric='coverage-ratio']").textContent = item.target_staff_count ? `${item.employee_count} من ${item.target_staff_count} موظفين` : "لم يُحدد العدد المستهدف لهذا الباب";
        card.querySelector("[data-metric='coverage-level']").textContent = item.target_staff_count ? item.staff_coverage_label : "";
        card.querySelector("[data-metric='coverage-detail']").textContent = item.target_staff_count ? item.staff_coverage_detail : "";
        card.querySelector("[data-detail='status']")?.replaceChildren(item.status_label);
        card.querySelector("[data-metric='activity']").textContent = item.last_activity ? new Date(item.last_activity).toLocaleString("ar-SA", { day: "numeric", month: "long", hour: "numeric", minute: "2-digit" }) : "لا يوجد نشاط مسجل";
        updateAlertIndicators(card, item.open_incident_count, item.active_maintenance_count);
      });
      Object.entries(payload.summary).forEach(([key, value]) => {
        document.querySelector(`[data-summary="${key}"]`)?.replaceChildren(String(value));
      });
      applyFilters();
      root.dispatchEvent(new CustomEvent("engineering:center-refreshed", { detail: payload }));
      const openButton = root.querySelector("[data-incident-followup][aria-expanded='true']");
      if (openButton) await loadFollowup(openButton, { preserve: true });
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
