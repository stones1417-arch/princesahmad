(() => {
  "use strict";
  const root = document.querySelector(".coverage-settings");
  if (!root) return;
  const rows = [...root.querySelectorAll("[data-coverage-row]")];
  const form = document.getElementById("coverageSettingsForm");
  const partial = Number(root.dataset.partial);
  const complete = Number(root.dataset.complete);
  const surplus = Number(root.dataset.surplus);
  const labels = {unconfigured: "غير مهيأة", suspended: "معلّقة", uncovered: "بدون تغطية", low: "تغطية منخفضة", partial: "تغطية جزئية", complete: "تغطية مكتملة", surplus: "فائض تشغيلي"};
  const suspendedReasons = {maintenance: "الباب تحت الصيانة", closed: "الباب مغلق تشغيليًا", secured: "الباب مؤمّن"};
  const initialCoveragePlan = Object.freeze({
    "1":3,"2":3,"3":2,"4":2,"5":3,"6B":4,"6A":4,"7":3,"8":3,"9":2,
    "10":2,"11":2,"12":3,"13":3,"14":2,"15":2,"16":2,"17":3,"18":3,"19":2,
    "20":2,"21":3,"22":3,"23":2,"24":2,"25":3,"26":3,"27":2,"28":2,"29":3,
    "30":3,"31":2,"32":2,"33":3,"34":3,"35":2,"36":2,"37":3,"38":3,"39":2,
    "40":2,"41":3
  });

  function coverage(current, rawTarget, status) {
    if (status !== "open") return {percent: null, level: "suspended", applicable: false};
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
    const result = coverage(Number(row.dataset.current), input.value.trim(), row.dataset.status);
    row.dataset.level = result.level;
    row.dataset.configuration = input.value.trim() ? "configured" : "unconfigured";
    row.querySelector("[data-preview-percent]").textContent = result.level === "suspended" ? "معلّقة" : result.percent === null ? "—" : `${result.percent}%`;
    const badge = row.querySelector("[data-preview-level]");
    badge.textContent = labels[result.level];
    badge.className = `coverage-level coverage-level--${result.level}`;
    const valid = input.value === "" || (Number.isInteger(Number(input.value)) && Number(input.value) >= 1 && Number(input.value) <= 999);
    input.setCustomValidity(valid ? "" : "أدخل عددًا صحيحًا من 1 إلى 999.");
    const ratio = row.querySelector("[data-preview-ratio]");
    const detail = row.querySelector("[data-preview-detail]");
    if (result.level === "suspended") {
      ratio.textContent = input.value ? `المستهدف: ${input.value} موظفين` : "";
      detail.textContent = suspendedReasons[row.dataset.status] || "تُستأنف عند عودة الباب للتشغيل";
    } else if (result.percent === null) {
      ratio.textContent = ""; detail.textContent = "لم يُحدد العدد المستهدف";
    } else {
      const current = Number(row.dataset.current); const target = Number(input.value);
      const difference = current - target;
      ratio.textContent = `${current} من ${target}`;
      detail.textContent = difference < 0 ? `نقص ${Math.abs(difference)} موظف` : difference > 0 ? `فائض ${difference} موظف` : "مكتملة";
    }
  }

  function updateDirty() {
    const dirty = rows.filter(row => {
      const input = row.querySelector(".coverage-target");
      return input && input.value.trim() !== row.dataset.original;
    }).length;
    const count = document.getElementById("dirtyCount");
    if (count) count.textContent = dirty;
    const total = rows.reduce((sum, row) => sum + (Number(row.querySelector(".coverage-target")?.value) || 0), 0);
    const totalPreview = document.getElementById("totalTargetPreview");
    if (totalPreview) totalPreview.textContent = total;
    const indicator = document.getElementById("unsavedPreviewIndicator");
    if (indicator) indicator.hidden = dirty === 0;
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
  const presetTrigger = document.getElementById("openCoveragePreset");
  const presetDialog = document.getElementById("coveragePresetDialog");
  const presetWarning = document.getElementById("presetWarning");
  presetTrigger?.addEventListener("click", () => presetDialog.showModal());
  presetDialog?.addEventListener("close", () => presetTrigger.focus());
  document.getElementById("applyCoveragePreset")?.addEventListener("click", () => {
    const rowNumbers = new Set(rows.map(row => row.dataset.number));
    const planNumbers = Object.keys(initialCoveragePlan);
    const catalogMatches = rows.length === planNumbers.length && planNumbers.every(number => rowNumbers.has(number));
    if (!catalogMatches) {
      presetDialog.close();
      presetWarning.textContent = "تعذر تحميل الخطة لأن كتالوج الأبواب لا يطابق الخطة الحالية.";
      presetWarning.hidden = false;
      return;
    }
    rows.forEach(row => {
      row.querySelector(".coverage-target").value = initialCoveragePlan[row.dataset.number];
      updateRow(row);
    });
    presetWarning.hidden = true;
    presetDialog.close();
    updateDirty(); filterRows();
  });
  form?.addEventListener("submit", event => { if (!form.checkValidity()) { event.preventDefault(); form.reportValidity(); } });
})();
