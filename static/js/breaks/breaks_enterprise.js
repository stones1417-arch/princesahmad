document.addEventListener("DOMContentLoaded", function () {
    "use strict";
    const notes = document.getElementById("breakCreateNotes");
    const count = document.getElementById("breakNotesCount");
    const form = document.getElementById("breakCreateForm");
    const save = form?.querySelector(".break-save-button");
    const search = document.getElementById("breakSearch");

    notes?.addEventListener("input", function () {
        count.textContent = `${notes.value.length}/1000`;
    });

    form?.addEventListener("submit", function () {
        if (!form.checkValidity() || !save) return;
        save.classList.add("is-loading");
        const label = save.querySelector("b");
        if (label) label.textContent = "جارٍ حفظ الراحة...";
    });

    document.addEventListener("keydown", function (event) {
        const tag = document.activeElement?.tagName || "";
        if (event.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(tag)) {
            event.preventDefault();
            search?.focus();
        }
    });
});
