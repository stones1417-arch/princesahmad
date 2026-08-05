document.addEventListener("DOMContentLoaded", function () {
    "use strict";
    const table = document.getElementById("distributionTable");
    const search = document.getElementById("distributionSearch");
    const counter = document.getElementById("distributionVisibleCounter");
    const form = document.getElementById("assignmentCreateForm");
    const submit = document.getElementById("assignmentSubmitButton");

    function updateVisibleCount() {
        if (!table || !counter) return;
        const rows = Array.from(table.querySelectorAll("tbody tr")).filter(function (row) {
            return !row.querySelector(".distribution-empty-row") && row.style.display !== "none";
        });
        counter.textContent = `${rows.length} توزيع`;
    }

    search?.addEventListener("input", function () {
        window.requestAnimationFrame(updateVisibleCount);
    });

    form?.addEventListener("submit", function () {
        if (!form.checkValidity() || !submit) return;
        submit.disabled = true;
        submit.classList.add("is-loading");
        const label = submit.querySelector("b");
        if (label) label.textContent = "جارٍ اعتماد التسكين...";
    });

    document.addEventListener("keydown", function (event) {
        const tag = document.activeElement?.tagName || "";
        if (event.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(tag)) {
            event.preventDefault();
            search?.focus();
        }
    });

    updateVisibleCount();
});
