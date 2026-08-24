(() => {
  "use strict";
  const tab = document.querySelector("#engineering3DMapTab");
  const panel = document.querySelector("#engineering3DMapPanel");
  if (!tab || !panel) return;
  let loading;
  const fallback = () => {
    panel.querySelector("[data-3d-loading]").hidden = true;
    panel.querySelector("[data-3d-fallback]").hidden = false;
  };
  tab.addEventListener("click", () => {
    if (loading) return;
    const probe = document.createElement("canvas");
    if (!probe.getContext("webgl2") && !probe.getContext("webgl")) { fallback(); return; }
    loading = import(panel.dataset.viewerModuleUrl).then((module) => module.mountEngineering3D(panel)).catch(fallback);
  });
  panel.querySelector("[data-3d-open-fallback]").addEventListener("click", () => document.querySelector("#engineeringOperationalMapTab").click());
})();
