(() => {
  "use strict";

  const root = document.querySelector(".engineering-center");
  const panel = document.querySelector("#engineeringOperationalMapPanel");
  if (!root || !panel) return;

  const namespace = "http://www.w3.org/2000/svg";
  const markerLayer = panel.querySelector("[data-map-markers]");
  const canvas = panel.querySelector("[data-map-canvas]");
  const viewport = panel.querySelector("[data-map-viewport]");
  const tooltip = panel.querySelector("[data-map-tooltip]");
  const drawer = panel.querySelector("[data-map-drawer]");
  const drawerContent = panel.querySelector("[data-map-drawer-content]");
  const connector = panel.querySelector("[data-map-connector]");
  const markers = new Map();
  const doorData = new Map();
  let initialized = false;
  let selectedDoor = null;
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let pointerStart = null;

  function cardFor(number) {
    return document.querySelector(`.engineering-card[data-number="${CSS.escape(number)}"]`);
  }

  function readCard(card) {
    return {
      id: card.dataset.doorId,
      number: card.dataset.number,
      status: card.dataset.status,
      statusLabel: card.querySelector("[data-metric='status']")?.textContent.trim() || card.dataset.status,
      employees: Number(card.dataset.employees),
      incidents: Number(card.dataset.incidents),
      maintenance: Number(card.dataset.maintenance),
      activity: card.querySelector("[data-metric='activity']")?.textContent.trim() || "لا يوجد نشاط مسجل",
    };
  }

  function hydrateFromCards() {
    document.querySelectorAll(".engineering-card").forEach((card) => {
      const item = readCard(card);
      doorData.set(item.number, item);
    });
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(namespace, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function badge(x, label, value, layer) {
    const group = svgElement("g", { class: "engineering-map-marker__badge", transform: `translate(${x} 22)`, "data-badge-layer": layer });
    group.append(svgElement("rect", { x: -18, y: -9, width: 36, height: 18, rx: 8 }));
    const text = svgElement("text", { y: 4 });
    text.textContent = `${label} ${value}`;
    group.append(text);
    return group;
  }

  function accessibleLabel(item) {
    return `الباب ${item.number}، ${item.statusLabel}، ${item.employees} موظفين، ${item.incidents} بلاغات، ${item.maintenance} طلبات صيانة`;
  }

  function renderMarker(position) {
    const item = doorData.get(position.door);
    if (!item) return;
    const group = svgElement("g", {
      class: "engineering-map-marker",
      transform: `translate(${position.x * 1000} ${position.y * 700})`,
      tabindex: "0",
      role: "button",
      "aria-label": accessibleLabel(item),
      "data-door": item.number,
      "data-status": item.status,
    });
    group.append(svgElement("circle", { class: "engineering-map-marker__ring", r: 24 }));
    group.append(svgElement("circle", { class: "engineering-map-marker__state", cx: -17, cy: -17, r: 6 }));
    const number = svgElement("text", { class: "engineering-map-marker__number", y: 5 });
    number.textContent = item.number;
    group.append(number);
    group.append(badge(-28, "م", item.employees, "employees"));
    group.append(badge(12, "ب", item.incidents, "incidents"));
    group.append(badge(52, "ص", item.maintenance, "maintenance"));
    group.addEventListener("mouseenter", (event) => showTooltip(item.number, event));
    group.addEventListener("mouseleave", hideTooltip);
    group.addEventListener("focus", (event) => showTooltip(item.number, event));
    group.addEventListener("blur", hideTooltip);
    group.addEventListener("click", () => selectDoor(item.number));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectDoor(item.number); }
    });
    markerLayer.append(group);
    markers.set(item.number, group);
    updateMarker(item.number);
  }

  function updateMarker(number) {
    const marker = markers.get(number);
    const item = doorData.get(number);
    if (!marker || !item) return;
    marker.dataset.status = item.status;
    marker.setAttribute("aria-label", accessibleLabel(item));
    marker.classList.toggle("has-alert", item.incidents > 0 || item.maintenance > 0);
    [["employees", item.employees], ["incidents", item.incidents], ["maintenance", item.maintenance]].forEach(([layer, value]) => {
      const node = marker.querySelector(`[data-badge-layer="${layer}"]`);
      node.querySelector("text").textContent = `${layer === "employees" ? "م" : layer === "incidents" ? "ب" : "ص"} ${value}`;
      node.hidden = value === 0 || !panel.querySelector(`[data-map-layer="${layer}"]`).checked;
    });
    marker.querySelector(".engineering-map-marker__state").hidden = !panel.querySelector("[data-map-layer='status']").checked;
  }

  function showTooltip(number, event) {
    const item = doorData.get(number);
    if (!item) return;
    tooltip.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = `الباب ${item.number} — ${item.statusLabel}`;
    tooltip.append(title);
    [
      `الموظفون: ${item.employees}`,
      `البلاغات: ${item.incidents}`,
      `الصيانة: ${item.maintenance}`,
      `آخر نشاط: ${item.activity}`,
      "اضغط لعرض التفاصيل",
    ].forEach((value) => { const span = document.createElement("span"); span.textContent = value; tooltip.append(span); });
    const rect = viewport.getBoundingClientRect();
    const x = event.clientX ? event.clientX - rect.left : rect.width / 2;
    const y = event.clientY ? event.clientY - rect.top : rect.height / 2;
    tooltip.style.left = `${Math.min(x + 12, rect.width - 275)}px`;
    tooltip.style.top = `${Math.max(8, y - 80)}px`;
    tooltip.hidden = false;
  }

  function hideTooltip() { tooltip.hidden = true; }

  function actionMarkup(number) {
    const card = cardFor(number);
    const links = [];
    const incident = card?.querySelector("[data-incident-action]");
    const distribution = card?.querySelector("[data-distribution-action]");
    const state = card?.querySelector("[data-door-state-action]");
    const maintenance = card?.querySelector(".engineering-card__drawer a[href*='/maintenance/']");
    links.push(`<button type="button" data-map-card-details="${number}">عرض التفاصيل</button>`);
    if (state) links.push(`<button type="button" data-map-state-proxy="${number}">تغيير الحالة</button>`);
    if (incident) links.push(`<a href="${incident.href}">إنشاء بلاغ</a>`);
    if (distribution) links.push(`<a href="${distribution.href}">عرض التوزيع</a>`);
    if (maintenance) links.push(`<a href="${maintenance.href}">عرض الصيانة</a>`);
    return links.join("");
  }

  function renderDrawer() {
    if (!selectedDoor) return;
    const item = doorData.get(selectedDoor);
    if (!item) return;
    drawerContent.innerHTML = `<small>التشغيل الحالي</small><h3>الباب ${item.number}</h3><span class="engineering-map-drawer__status">${item.statusLabel}</span><dl><div><dt>الموظفون</dt><dd>${item.employees}</dd></div><div><dt>البلاغات المفتوحة</dt><dd>${item.incidents}</dd></div><div><dt>طلبات الصيانة</dt><dd>${item.maintenance}</dd></div><div><dt>آخر نشاط</dt><dd>${item.activity}</dd></div></dl><h4>الإجراءات</h4><nav>${actionMarkup(item.number)}</nav>`;
    drawer.hidden = false;
    drawerContent.querySelector("[data-map-card-details]")?.addEventListener("click", () => {
      const button = cardFor(item.number)?.querySelector(".engineering-card__details");
      document.querySelector("#engineeringOverviewTab")?.click();
      button?.click();
      button?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    drawerContent.querySelector("[data-map-state-proxy]")?.addEventListener("click", () => cardFor(item.number)?.querySelector("[data-door-state-action]")?.click());
  }

  function selectDoor(number) {
    markers.get(selectedDoor)?.classList.remove("is-selected");
    selectedDoor = number;
    const marker = markers.get(number);
    marker?.classList.add("is-selected");
    markerLayer.classList.add("has-selection");
    const coordinates = marker?.getAttribute("transform")?.match(/translate\(([-.\d]+) ([-.\d]+)\)/);
    if (coordinates) {
      connector.setAttribute("x1", coordinates[1]);
      connector.setAttribute("y1", coordinates[2]);
      connector.hidden = false;
    }
    renderDrawer();
  }

  function applyTransform() { canvas.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`; }
  function zoom(delta) { scale = Math.min(3, Math.max(.75, scale + delta)); applyTransform(); }
  function resetView() { scale = 1; translateX = 0; translateY = 0; applyTransform(); }

  function matches(item) {
    const query = panel.querySelector("[data-map-search]").value.trim().toLowerCase();
    const status = panel.querySelector("[data-map-filter='status']").value;
    const yesNo = (name, value) => { const filter = panel.querySelector(`[data-map-filter='${name}']`).value; return filter === "all" || (filter === "yes") === (value > 0); };
    return (!query || item.number.toLowerCase().includes(query)) && (status === "all" || item.status === status) && yesNo("employees", item.employees) && yesNo("incidents", item.incidents) && yesNo("maintenance", item.maintenance);
  }

  function applyFilters() {
    let count = 0;
    doorData.forEach((item, number) => { const match = matches(item); markers.get(number)?.classList.toggle("is-dimmed", !match); if (match) count += 1; });
    panel.querySelector("[data-map-result-count]").textContent = `مطابق: ${count} من ${doorData.size}`;
    const query = panel.querySelector("[data-map-search]").value.trim().toLowerCase();
    const exact = [...doorData.values()].find((item) => item.number.toLowerCase() === query);
    if (exact) { selectDoor(exact.number); markers.get(exact.number)?.focus(); }
  }

  function updateSummary(summary = null) {
    const items = [...doorData.values()];
    const value = summary || {
      total_doors: items.length,
      working_doors: items.filter((item) => item.status === "open").length,
      stopped_doors: items.filter((item) => ["closed", "secured"].includes(item.status)).length,
      maintenance_doors: items.filter((item) => item.status === "maintenance").length,
      assigned_employees: items.reduce((sum, item) => sum + item.employees, 0),
      open_incidents: items.reduce((sum, item) => sum + item.incidents, 0),
      active_maintenance: items.reduce((sum, item) => sum + item.maintenance, 0),
    };
    panel.querySelector("[data-map-summary]").innerHTML = `<span>${value.total_doors} بابًا</span><span>● ${value.working_doors} مفتوح</span><span>● ${value.maintenance_doors} صيانة</span><span>● ${value.stopped_doors} متوقف/مغلق</span><span>👥 ${value.assigned_employees} موظف</span><span>⚠ ${value.open_incidents} بلاغات</span><span>◆ ${value.active_maintenance} طلب صيانة</span>`;
  }

  async function initialize() {
    if (initialized) return;
    initialized = true;
    hydrateFromCards();
    const response = await fetch(panel.dataset.layoutUrl);
    if (!response.ok) throw new Error("Operational map layout failed to load");
    const layout = await response.json();
    layout.doors.forEach(renderMarker);
    updateSummary();
    applyFilters();
  }

  panel.querySelectorAll("[data-map-filter]").forEach((control) => control.addEventListener("change", applyFilters));
  panel.querySelector("[data-map-search]").addEventListener("input", applyFilters);
  panel.querySelectorAll("[data-map-layer]").forEach((control) => control.addEventListener("change", () => doorData.forEach((_, number) => updateMarker(number))));
  panel.querySelectorAll("[data-map-mode]").forEach((button) => button.addEventListener("click", () => {
    const mode = button.dataset.mapMode;
    panel.querySelectorAll("[data-map-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    panel.querySelector("[data-map-visual='model']").hidden = mode !== "model";
    panel.querySelector("[data-map-visual='schematic']").hidden = mode !== "schematic";
  }));
  panel.querySelector("[data-map-zoom='in']").addEventListener("click", () => zoom(.2));
  panel.querySelector("[data-map-zoom='out']").addEventListener("click", () => zoom(-.2));
  panel.querySelector("[data-map-reset]").addEventListener("click", resetView);
  panel.querySelector("[data-map-show-all]").addEventListener("click", () => { panel.querySelector("[data-map-search]").value = ""; panel.querySelectorAll("[data-map-filter]").forEach((control) => { control.value = "all"; }); applyFilters(); resetView(); });
  const fullscreenButton = panel.querySelector("[data-map-fullscreen]");
  fullscreenButton.addEventListener("click", () => {
    if (document.fullscreenElement === panel.querySelector("[data-map-workspace]")) document.exitFullscreen?.();
    else panel.querySelector("[data-map-workspace]").requestFullscreen?.();
  });
  document.addEventListener("fullscreenchange", () => {
    fullscreenButton.textContent = document.fullscreenElement === panel.querySelector("[data-map-workspace]") ? "خروج" : "ملء الشاشة";
  });
  panel.querySelector("[data-map-drawer-close]").addEventListener("click", () => { drawer.hidden = true; markers.get(selectedDoor)?.classList.remove("is-selected"); markerLayer.classList.remove("has-selection"); connector.hidden = true; selectedDoor = null; });
  viewport.addEventListener("keydown", (event) => { if (["+", "="].includes(event.key)) zoom(.2); if (event.key === "-") zoom(-.2); if (event.key === "Escape") drawer.hidden = true; });
  viewport.addEventListener("wheel", (event) => { if (!event.ctrlKey) return; event.preventDefault(); zoom(event.deltaY < 0 ? .15 : -.15); }, { passive: false });
  viewport.addEventListener("pointerdown", (event) => { if (event.target.closest(".engineering-map-marker")) return; pointerStart = { x: event.clientX, y: event.clientY, tx: translateX, ty: translateY }; viewport.setPointerCapture(event.pointerId); });
  viewport.addEventListener("pointermove", (event) => { if (!pointerStart) return; translateX = pointerStart.tx + event.clientX - pointerStart.x; translateY = pointerStart.ty + event.clientY - pointerStart.y; applyTransform(); });
  viewport.addEventListener("pointerup", () => { pointerStart = null; });
  document.querySelector("#engineeringOperationalMapTab").addEventListener("click", () => initialize().catch(() => { panel.querySelector("[data-map-result-count]").textContent = "تعذر تحميل تكوين المخطط"; }));
  root.addEventListener("engineering:center-refreshed", (event) => {
    event.detail.doors.forEach((item) => {
      const current = doorData.get(item.number);
      if (!current) return;
      doorData.set(item.number, { ...current, status: item.status, statusLabel: item.status_label, employees: item.employee_count, incidents: item.open_incident_count, maintenance: item.active_maintenance_count, activity: item.last_activity ? new Date(item.last_activity).toLocaleString("ar-SA", { hour: "numeric", minute: "2-digit" }) : "لا يوجد نشاط مسجل" });
      updateMarker(item.number);
    });
    updateSummary(event.detail.summary);
    applyFilters();
    if (selectedDoor) renderDrawer();
  });
})();
