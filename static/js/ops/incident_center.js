document.addEventListener("DOMContentLoaded", () => {
  const createDrawer = document.getElementById("incidentCreateDrawer");
  const createTrigger = document.querySelector("[data-create-drawer-open]");
  const closeCreate = () => {
    if (!createDrawer?.open) return;
    createDrawer.close();
    document.body.classList.remove("incident-center-drawer-open");
    createTrigger?.focus();
  };
  createTrigger?.addEventListener("click", () => {
    createDrawer.showModal();
    document.body.classList.add("incident-center-drawer-open");
    createDrawer.querySelector("select, input, textarea, button")?.focus();
  });
  createDrawer?.querySelector("[data-create-drawer-close]")?.addEventListener("click", closeCreate);
  createDrawer?.addEventListener("cancel", (event) => { event.preventDefault(); closeCreate(); });
  createDrawer?.addEventListener("click", (event) => { if (event.target === createDrawer) closeCreate(); });
  if (createDrawer && new URLSearchParams(window.location.search).get("create") === "1") createTrigger?.click();

  const tabButtons = [...document.querySelectorAll("[data-incident-tab]")];
  const incidentRows = [...document.querySelectorAll("#incidentTableBody tr[data-id]")];
  tabButtons.forEach((button) => button.addEventListener("click", () => {
    const tab = button.dataset.incidentTab;
    tabButtons.forEach((item) => item.toggleAttribute("aria-current", item === button));
    incidentRows.forEach((row) => { row.hidden = tab !== "all" && !row.dataset.incidentState.split(" ").includes(tab); });
  }));
  let actionTrigger = null;
  document.querySelectorAll(".incident-escalate-button,.incident-convert-button,.incident-close-button").forEach((button) => {
    button.addEventListener("click", () => { actionTrigger = button; }, { capture: true });
  });
  document.querySelectorAll(".incident-action-dialog").forEach((dialog) => {
    dialog.addEventListener("close", () => { actionTrigger?.focus(); actionTrigger = null; });
  });
  const drawer = document.getElementById("incidentCenterDrawer");
  if (drawer) {
    const content = drawer.querySelector("[data-drawer-content]");
    let trigger = null;
    const close = () => { drawer.close(); trigger?.focus(); };
    document.querySelectorAll("[data-incident-detail]").forEach((button) => {
      button.addEventListener("click", () => {
        const source = document.getElementById(button.dataset.incidentDetail);
        if (!source) return;
        trigger = button;
        content.innerHTML = source.innerHTML;
        drawer.showModal();
        drawer.querySelector("[data-drawer-close]").focus();
      });
    });
    drawer.querySelector("[data-drawer-close]").addEventListener("click", close);
    drawer.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  }
  const createForm = document.getElementById("incidentCreateForm");
  createForm?.addEventListener("submit", () => {
    const button = document.getElementById("incidentSaveButton");
    if (!button || button.disabled) return;
    button.disabled = true;
    const label = document.getElementById("incidentSaveButtonText");
    if (label) label.textContent = "جاري إنشاء البلاغ...";
  });
});
