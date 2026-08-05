document.addEventListener("DOMContentLoaded", function () {
    "use strict";
    const search = document.getElementById("reportsLiveSearch");
    const rows = Array.from(document.querySelectorAll("[data-report-list-row]"));
    const counter = document.getElementById("reportsVisibleCount");

    function filterRows() {
        const query = search?.value.trim().toLowerCase() || "";
        let visible = 0;
        rows.forEach(function (row) {
            row.hidden = !!query && !row.textContent.toLowerCase().includes(query);
            if (!row.hidden) visible += 1;
        });
        if (counter) counter.textContent = `${visible} تقرير`;
    }
    search?.addEventListener("input", filterRows);
    document.addEventListener("keydown", function (event) {
        if (event.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) { event.preventDefault(); search?.focus(); }
    });
});
