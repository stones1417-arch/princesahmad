/* =========================================================
   منصة أبواب — إدارة الراحات الأسبوعية
   المسار: static/js/breaks/break_list.js

   الوظائف:
   - الملخص المباشر لنموذج الإضافة.
   - عرض تفاصيل الراحة.
   - تعديل الراحة داخل نافذة مستقلة.
   - تعبئة نموذج التعديل تلقائيًا.
   - منع إرسال النماذج أكثر من مرة.
   - رسائل تأكيد الحذف والتفعيل والتعطيل.
   - إغلاق النوافذ بالضغط على Escape.
   - إزالة رسائل النظام تلقائيًا.
========================================================= */

(() => {
    "use strict";

    /* =====================================================
       أدوات DOM
    ===================================================== */

    const byId = (id) => document.getElementById(id);

    const detailsModal = byId("breakDetailsModal");
    const editModal = byId("breakEditModal");

    const employeeSelect = byId("employeeSelect");
    const shiftSelect = byId("shiftSelect");
    const jobTitleSelect = byId("jobTitleSelect");
    const restDaysSelect = byId("restDaysSelect");

    const editForm = byId("breakEditForm");
    const editEmployeeSelect = byId("editEmployeeSelect");
    const editShiftSelect = byId("editShiftSelect");
    const editJobTitleSelect = byId("editJobTitleSelect");
    const editRestDaysSelect = byId("editRestDaysSelect");
    const editNotes = byId("editNotes");
    const editChangeReason = byId("editChangeReason");
    const editSubmitButton = byId("breakEditSubmit");
    const editCloseButton = byId("breakEditModalClose");

    let lastFocusedElement = null;
    let editFormSubmitting = false;


    /* =====================================================
       أدوات مساعدة
    ===================================================== */

    function safeText(value, fallback = "—") {
        const text = String(value ?? "").trim();

        return text || fallback;
    }


    function setText(id, value, fallback = "—") {
        const element = byId(id);

        if (!element) {
            return;
        }

        element.textContent = safeText(
            value,
            fallback
        );
    }


    function normalizeId(value) {
        return String(value ?? "").trim();
    }


    function scrollToSection(id) {
        const section = byId(id);

        if (!section) {
            return;
        }

        section.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }


    function selectedOption(selectElement) {
        if (
            !selectElement
            || selectElement.selectedIndex < 0
        ) {
            return null;
        }

        return (
            selectElement.options[
                selectElement.selectedIndex
            ] || null
        );
    }


    function selectValue(
        selectElement,
        value
    ) {
        if (!selectElement) {
            return false;
        }

        const normalizedValue = normalizeId(
            value
        );

        const optionExists = Array
            .from(selectElement.options)
            .some((option) => (
                normalizeId(option.value)
                === normalizedValue
            ));

        if (!optionExists) {
            selectElement.value = "";
            return false;
        }

        selectElement.value = normalizedValue;

        return true;
    }


    function lockBodyScroll() {
        document.body.classList.add(
            "break-modal-open"
        );

        document.body.style.overflow = "hidden";
    }


    function unlockBodyScroll() {
        const detailsIsOpen = (
            detailsModal
            && detailsModal.classList.contains("active")
        );

        const editIsOpen = (
            editModal
            && editModal.classList.contains("active")
        );

        if (!detailsIsOpen && !editIsOpen) {
            document.body.classList.remove(
                "break-modal-open"
            );

            document.body.style.overflow = "";
        }
    }


    function restoreLastFocus() {
        if (
            lastFocusedElement
            && typeof lastFocusedElement.focus === "function"
            && document.contains(lastFocusedElement)
        ) {
            lastFocusedElement.focus();
        }

        lastFocusedElement = null;
    }


    function setButtonLoading(
        button,
        loading,
        loadingText = "جارٍ الحفظ..."
    ) {
        if (!button) {
            return;
        }

        if (loading) {
            const label = button.querySelector("b");

            if (label) {
                if (!button.dataset.originalLabel) {
                    button.dataset.originalLabel = label.textContent.trim();
                }
                button.disabled = true;
                button.setAttribute("aria-busy", "true");
                button.classList.add("is-loading");
                label.textContent = loadingText;
                return;
            }

            if (!button.dataset.originalText) {
                button.dataset.originalText = (
                    button.textContent || ""
                ).trim();
            }

            button.disabled = true;
            button.setAttribute(
                "aria-busy",
                "true"
            );

            button.textContent = loadingText;

            return;
        }

        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.classList.remove("is-loading");

        const label = button.querySelector("b");
        if (label && button.dataset.originalLabel) {
            label.textContent = button.dataset.originalLabel;
            delete button.dataset.originalLabel;
            return;
        }

        if (button.dataset.originalText) {
            button.textContent = (
                button.dataset.originalText
            );

            delete button.dataset.originalText;
        }
    }


    /* =====================================================
       التنقل داخل الصفحة
    ===================================================== */

    window.scrollToBreakCreate = function () {
        scrollToSection(
            "break-create-section"
        );
    };


    window.scrollToBreakList = function () {
        scrollToSection(
            "break-list-section"
        );
    };


    /* =====================================================
       الملخص المباشر لنموذج الإضافة
    ===================================================== */

    function updateCreatePreview() {
        const employeeOption = selectedOption(
            employeeSelect
        );

        const shiftOption = selectedOption(
            shiftSelect
        );

        const jobOption = selectedOption(
            jobTitleSelect
        );

        const restOption = selectedOption(
            restDaysSelect
        );

        setText(
            "previewEmployee",
            employeeOption?.dataset.name
        );

        setText(
            "previewEmployeeNumber",
            employeeOption?.dataset.number
        );

        setText(
            "previewShift",
            shiftOption?.dataset.name
        );

        setText(
            "previewJob",
            jobOption?.dataset.name
        );

        setText(
            "previewRest",
            restOption?.dataset.name
        );
    }


    [
        employeeSelect,
        shiftSelect,
        jobTitleSelect,
        restDaysSelect,
    ].forEach((element) => {
        if (!element) {
            return;
        }

        element.addEventListener(
            "change",
            updateCreatePreview
        );
    });

    updateCreatePreview();


    /* =====================================================
       منع إرسال نموذج الإضافة أكثر من مرة
    ===================================================== */

    const createForm = byId(
        "breakCreateForm"
    );

    if (createForm) {
        createForm.addEventListener(
            "submit",
            (event) => {
                if (
                    createForm.dataset.submitting
                    === "true"
                ) {
                    event.preventDefault();
                    return;
                }

                if (!createForm.checkValidity()) {
                    return;
                }

                createForm.dataset.submitting = "true";

                const submitButton = (
                    createForm.querySelector(
                        ".break-save-button"
                    )
                );

                setButtonLoading(
                    submitButton,
                    true,
                    "جارٍ حفظ الراحة..."
                );
            }
        );
    }


    /* =====================================================
       نافذة تفاصيل الراحة
    ===================================================== */

    window.openBreakDetails = function (
        id,
        employee,
        number,
        shift,
        job,
        rest,
        notes,
        status,
        created,
        updated
    ) {
        if (!detailsModal) {
            return;
        }

        lastFocusedElement = (
            document.activeElement
        );

        const employeeName = safeText(
            employee
        );

        const employeeAvatar = (
            employeeName.charAt(0) || "م"
        );

        setText(
            "modalEmployeeAvatar",
            employeeAvatar,
            "م"
        );

        setText(
            "modalEmployeeName",
            employeeName
        );

        setText(
            "modalEmployeeNumber",
            number
        );

        setText(
            "modalShift",
            shift
        );

        setText(
            "modalJob",
            job
        );

        setText(
            "modalRestDays",
            rest
        );

        setText(
            "modalNotes",
            notes,
            "لا توجد ملاحظات"
        );

        setText(
            "modalCreatedAt",
            created
        );

        setText(
            "modalUpdatedAt",
            updated
        );

        const statusBadge = byId(
            "modalBreakStatus"
        );

        const isActive = (
            safeText(status, "")
            === "نشط"
        );

        if (statusBadge) {
            statusBadge.textContent = (
                isActive
                    ? "نشط"
                    : "غير نشط"
            );

            statusBadge.className = (
                "break-modal-status "
                + (
                    isActive
                        ? "active"
                        : "inactive"
                )
            );
        }

        detailsModal.dataset.breakId = (
            normalizeId(id)
        );

        detailsModal.classList.add(
            "active"
        );

        detailsModal.setAttribute(
            "aria-hidden",
            "false"
        );

        lockBodyScroll();

        const closeButton = (
            detailsModal.querySelector(
                ".break-modal-close"
            )
        );

        if (closeButton) {
            closeButton.focus();
        }
    };


    window.closeBreakDetails = function () {
        if (!detailsModal) {
            return;
        }

        detailsModal.classList.remove(
            "active"
        );

        detailsModal.setAttribute(
            "aria-hidden",
            "true"
        );

        delete detailsModal.dataset.breakId;

        unlockBodyScroll();
        restoreLastFocus();
    };


    /* =====================================================
       نافذة تعديل الراحة
    ===================================================== */

    function updateEditEmployeeSummary() {
        const option = selectedOption(
            editEmployeeSelect
        );

        const name = (
            option?.dataset.name || "—"
        );

        const number = (
            option?.dataset.number || "—"
        );

        setText(
            "editEmployeeName",
            name
        );

        setText(
            "editEmployeeNumber",
            number
        );

        setText(
            "editEmployeeAvatar",
            (
                safeText(name, "م")
                .charAt(0)
            ),
            "م"
        );
    }


    window.openBreakEdit = function (
        id,
        employeeId,
        employeeName,
        employeeNumber,
        shiftTypeId,
        jobTitle,
        restDays,
        notes,
        updateUrl
    ) {
        if (
            !editModal
            || !editForm
        ) {
            return;
        }

        lastFocusedElement = (
            document.activeElement
        );

        editFormSubmitting = false;

        editForm.dataset.breakId = (
            normalizeId(id)
        );

        editForm.action = safeText(
            updateUrl,
            ""
        );

        selectValue(
            editEmployeeSelect,
            employeeId
        );

        selectValue(
            editShiftSelect,
            shiftTypeId
        );

        selectValue(
            editJobTitleSelect,
            jobTitle
        );

        selectValue(
            editRestDaysSelect,
            restDays
        );

        if (editNotes) {
            editNotes.value = (
                notes ?? ""
            );
        }

        if (editChangeReason) {
            editChangeReason.value = "";
        }

        setText(
            "editEmployeeName",
            employeeName
        );

        setText(
            "editEmployeeNumber",
            employeeNumber
        );

        setText(
            "editEmployeeAvatar",
            (
                safeText(
                    employeeName,
                    "م"
                ).charAt(0)
            ),
            "م"
        );

        setButtonLoading(
            editSubmitButton,
            false
        );

        editModal.classList.add(
            "active"
        );

        editModal.setAttribute(
            "aria-hidden",
            "false"
        );

        lockBodyScroll();

        window.setTimeout(() => {
            if (editEmployeeSelect) {
                editEmployeeSelect.focus();
            }
        }, 50);
    };


    window.closeBreakEdit = function () {
        if (!editModal) {
            return;
        }

        if (editFormSubmitting) {
            return;
        }

        editModal.classList.remove(
            "active"
        );

        editModal.setAttribute(
            "aria-hidden",
            "true"
        );

        if (editForm) {
            editForm.removeAttribute(
                "data-break-id"
            );
        }

        if (editChangeReason) {
            editChangeReason.value = "";
        }

        setButtonLoading(
            editSubmitButton,
            false
        );

        unlockBodyScroll();
        restoreLastFocus();
    };


    if (editEmployeeSelect) {
        editEmployeeSelect.addEventListener(
            "change",
            updateEditEmployeeSummary
        );
    }


    if (editCloseButton) {
        editCloseButton.addEventListener(
            "click",
            window.closeBreakEdit
        );
    }


    document
        .querySelectorAll(
            "[data-close-break-edit]"
        )
        .forEach((element) => {
            element.addEventListener(
                "click",
                window.closeBreakEdit
            );
        });


    /* =====================================================
       التحقق من نموذج التعديل
    ===================================================== */

    if (editForm) {
        editForm.addEventListener(
            "submit",
            (event) => {
                if (editFormSubmitting) {
                    event.preventDefault();
                    return;
                }

                if (!editForm.action) {
                    event.preventDefault();

                    window.alert(
                        "تعذر تحديد رابط تعديل الراحة."
                    );

                    return;
                }

                if (!editForm.checkValidity()) {
                    return;
                }

                const reason = safeText(
                    editChangeReason?.value,
                    ""
                );

                if (reason.length < 3) {
                    event.preventDefault();

                    window.alert(
                        "يرجى كتابة سبب واضح للتعديل."
                    );

                    if (editChangeReason) {
                        editChangeReason.focus();
                    }

                    return;
                }

                const confirmed = window.confirm(
                    "هل أنت متأكد من حفظ تعديلات الراحة؟"
                );

                if (!confirmed) {
                    event.preventDefault();
                    return;
                }

                editFormSubmitting = true;

                setButtonLoading(
                    editSubmitButton,
                    true,
                    "جارٍ حفظ التعديلات..."
                );
            }
        );
    }


    /* =====================================================
       رسائل تأكيد العمليات
    ===================================================== */

    window.confirmBreakDelete = function (name) {
        const employeeName = safeText(
            name,
            "الموظف"
        );

        return window.confirm(
            "سيتم حذف راحة الموظف:\n\n"
            + employeeName
            + "\n\n"
            + "سيبقى سجل العملية محفوظًا في سجل التدقيق.\n"
            + "هل تريد المتابعة؟"
        );
    };


    window.confirmBreakToggle = function (
        action,
        name
    ) {
        const actionName = safeText(
            action,
            "تحديث"
        );

        const employeeName = safeText(
            name,
            "الموظف"
        );

        return window.confirm(
            "هل تريد "
            + actionName
            + " راحة الموظف:\n\n"
            + employeeName
            + "؟"
        );
    };


    /* =====================================================
       منع إرسال نماذج الجدول أكثر من مرة
    ===================================================== */

    document
        .querySelectorAll(
            ".break-inline-form"
        )
        .forEach((form) => {
            form.addEventListener(
                "submit",
                (event) => {
                    if (
                        form.dataset.submitting
                        === "true"
                    ) {
                        event.preventDefault();
                        return;
                    }

                    form.dataset.submitting = "true";

                    const button = (
                        form.querySelector(
                            "button[type='submit']"
                        )
                    );

                    if (button) {
                        button.disabled = true;
                        button.setAttribute(
                            "aria-busy",
                            "true"
                        );
                    }
                }
            );
        });


    /* =====================================================
       إغلاق النوافذ بلوحة المفاتيح
    ===================================================== */

    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key !== "Escape") {
                return;
            }

            if (
                editModal
                && editModal.classList.contains(
                    "active"
                )
            ) {
                window.closeBreakEdit();
                return;
            }

            if (
                detailsModal
                && detailsModal.classList.contains(
                    "active"
                )
            ) {
                window.closeBreakDetails();
            }
        }
    );


    /* =====================================================
       منع الإغلاق عند الضغط داخل النافذة
    ===================================================== */

    document
        .querySelectorAll(
            ".break-modal-dialog"
        )
        .forEach((dialog) => {
            dialog.addEventListener(
                "click",
                (event) => {
                    event.stopPropagation();
                }
            );
        });


    /* =====================================================
       تحسين رسائل النظام
    ===================================================== */

    const systemMessages = (
        document.querySelectorAll(
            ".breaks-message"
        )
    );

    systemMessages.forEach(
        (message, index) => {
            const timeout = (
                5000
                + (index * 350)
            );

            window.setTimeout(() => {
                if (!message.isConnected) {
                    return;
                }

                message.style.transition = (
                    "opacity .25s ease, "
                    + "transform .25s ease"
                );

                message.style.opacity = "0";

                message.style.transform = (
                    "translateY(-8px)"
                );

                window.setTimeout(() => {
                    if (message.isConnected) {
                        message.remove();
                    }
                }, 260);
            }, timeout);
        }
    );


    /* =====================================================
       إغلاق الرسائل يدويًا
    ===================================================== */

    document
        .querySelectorAll(
            ".breaks-message-close"
        )
        .forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    const message = button.closest(
                        ".breaks-message"
                    );

                    if (message) {
                        message.remove();
                    }
                }
            );
        });


    /* =====================================================
       التهيئة
    ===================================================== */

    updateEditEmployeeSummary();
})();
