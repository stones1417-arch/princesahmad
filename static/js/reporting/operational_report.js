document.addEventListener("DOMContentLoaded", function () {
    "use strict";
    const clock = document.getElementById("operationalLiveClock");
    function updateClock() {
        if (clock) clock.textContent = new Intl.DateTimeFormat("ar-SA", {hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date());
    }
    function filterTable(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        const search = document.querySelector(`[data-report-search="${tableId}"]`);
        const state = document.querySelector(`[data-table-state-filter="${tableId}"]`)?.value || "";
        const role = document.querySelector(`[data-table-role-filter="${tableId}"]`)?.value || "";
        const query = search?.value.trim().toLowerCase() || "";
        let visible = 0;
        table.querySelectorAll("[data-report-row]").forEach(function (row) {
            row.hidden = !((!query || row.textContent.toLowerCase().includes(query)) && (!state || row.dataset.state === state) && (!role || row.dataset.role === role));
            if (!row.hidden) visible += 1;
        });
        const target = document.getElementById(table.dataset.countTarget);
        if (target) target.textContent = `${visible} ${table.dataset.countLabel}`;
    }
    document.querySelectorAll("[data-report-search]").forEach(function (input) { input.addEventListener("input", function () { filterTable(input.dataset.reportSearch); }); });
    document.querySelectorAll("[data-table-state-filter]").forEach(function (select) { select.addEventListener("change", function () { filterTable(select.dataset.tableStateFilter); }); });
    document.querySelectorAll("[data-table-role-filter]").forEach(function (select) { select.addEventListener("change", function () { filterTable(select.dataset.tableRoleFilter); }); });
    document.addEventListener("keydown", function (event) {
        if (event.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) { event.preventDefault(); document.querySelector("[data-report-search]")?.focus(); }
    });
    updateClock(); window.setInterval(updateClock, 1000);
});
