document.addEventListener("DOMContentLoaded", () => {
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
