(function () {
    "use strict";
    document.querySelectorAll(".assignment-confirm-form").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            if (form.dataset.confirmed === "true") return;
            event.preventDefault();
            const confirmed = await window.confirmAppAction({
                title: "تأكيد إضافة الدور",
                message: `سيتم إضافة دور «${form.dataset.roleName}» إلى ${form.dataset.employeeName} وتحديث صلاحياته الفعلية فورًا. هل تريد المتابعة؟`,
                confirmText: "اعتماد التسكين",
                cancelText: "مراجعة الاختيار",
                type: "primary",
            });
            if (confirmed) {
                form.dataset.confirmed = "true";
                form.requestSubmit();
            }
        });
    });
})();
