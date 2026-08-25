(() => {
  "use strict";
  const root = document.querySelector(".coverage-settings");
  if (!root) return;
  const rows = [...root.querySelectorAll("[data-coverage-row]")];
  const form = document.getElementById("coverageSettingsForm");
  const partial = Number(root.dataset.partial);
  const complete = Number(root.dataset.complete);
  const surplus = Number(root.dataset.surplus);
  const labels = {unconfigured: "غير مهيأة", uncovered: "بدون تغطية", low: "تغطية منخفضة", partial: "تغطية جزئية", complete: "تغطية مكتملة", surplus: "فائض تشغيلي"};

  function coverage(current, rawTarget) {
    if (rawTarget === "") return {percent: null, level: "unconfigured"};
    const target = Number(rawTarget);
    if (!Number.isInteger(target) || target < 1 || target > 999) return {percent: null, level: "unconfigured"};
    const percent = Math.round((current / target) * 100);
    if (current === 0) return {percent, level: "uncovered"};
    if (percent < partial) return {percent, level: "low"};
    if (percent < complete) return {percent, level: "partial"};
    if (percent < surplus) return {percent, level: "complete"};
    return {percent, level: "surplus"};
  }

  function updateRow(row) {
    const input = row.querySelector(".coverage-target");
    if (!input) return;
    const result = coverage(Number(row.dataset.current), input.value.trim());
    row.dataset.level = result.level;
    row.dataset.configuration = input.value.trim() ? "configured" : "unconfigured";
    row.querySelector("[data-preview-percent]").textContent = result.percent === null ? "—" : `${result.percent}%`;
    const badge = row.querySelector("[data-preview-level]");
    badge.textContent = labels[result.level];
    badge.className = `coverage-level coverage-level--${result.level}`;
    const valid = input.value === "" || (Number.isInteger(Number(input.value)) && Number(input.value) >= 1 && Number(input.value) <= 999);
    input.setCustomValidity(valid ? "" : "أدخل عددًا صحيحًا من 1 إلى 999.");
  }

  function updateDirty() {
    const dirty = rows.filter(row => {
      const input = row.querySelector(".coverage-target");
      return input && input.value.trim() !== row.dataset.original;
    }).length;
    const count = document.getElementById("dirtyCount");
    if (count) count.textContent = dirty;
    ["saveCoverageSettings", "resetCoverageChanges"].forEach(id => {
      const button = document.getElementById(id);
      if (button) button.disabled = dirty === 0;
    });
  }

  function filterRows() {
    const query = document.getElementById("coverageSearch").value.trim();
    const status = document.getElementById("coverageStatus").value;
    const configuration = document.getElementById("configurationFilter").value;
    const level = document.getElementById("coverageLevel").value;
    rows.forEach(row => {
      row.hidden = !(
        (!query || row.dataset.number.includes(query)) &&
        (status === "all" || row.dataset.status === status) &&
        (configuration === "all" || row.dataset.configuration === configuration) &&
        (level === "all" || row.dataset.level === level)
      );
    });
  }

  rows.forEach(row => {
    const input = row.querySelector(".coverage-target");
    if (input) {
      updateRow(row);
      input.addEventListener("input", () => { updateRow(row); updateDirty(); filterRows(); });
    }
    const checkbox = row.querySelector(".coverage-select");
    if (checkbox) checkbox.addEventListener("change", updateSelected);
  });
  function updateSelected() {
    const selected = rows.filter(row => row.querySelector(".coverage-select")?.checked).length;
    const count = document.getElementById("selectedCount");
    if (count) count.textContent = selected;
    const apply = document.getElementById("applyBulkTarget");
    if (apply) apply.disabled = selected === 0;
  }
  ["coverageSearch", "coverageStatus", "configurationFilter", "coverageLevel"].forEach(id => document.getElementById(id)?.addEventListener("input", filterRows));
  document.getElementById("resetCoverageFilters")?.addEventListener("click", () => {
    document.getElementById("coverageSearch").value = "";
    ["coverageStatus", "configurationFilter", "coverageLevel"].forEach(id => document.getElementById(id).value = "all");
    filterRows();
  });
  document.getElementById("applyBulkTarget")?.addEventListener("click", () => {
    const bulk = document.getElementById("bulkTarget");
    if (!bulk.reportValidity() || bulk.value === "") return;
    rows.forEach(row => {
      if (row.querySelector(".coverage-select")?.checked) {
        row.querySelector(".coverage-target").value = bulk.value;
        updateRow(row);
      }
    });
    updateDirty(); filterRows();
  });
  document.getElementById("resetCoverageChanges")?.addEventListener("click", () => {
    rows.forEach(row => { const input = row.querySelector(".coverage-target"); if (input) { input.value = row.dataset.original; updateRow(row); } });
    updateDirty(); filterRows();
  });
  form?.addEventListener("submit", event => { if (!form.checkValidity()) { event.preventDefault(); form.reportValidity(); } });
})();
