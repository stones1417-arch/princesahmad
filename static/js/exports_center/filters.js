"use strict";

(function () {
    const page = document.getElementById(
        "exportFilterCenter"
    );

    if (!page) {
        return;
    }

    const form = document.getElementById(
        "exportFiltersForm"
    );

    if (!form) {
        return;
    }

    const activeSection = document.getElementById(
        "xefActiveFiltersSection"
    );

    const activeContainer = document.getElementById(
        "xefActiveFilters"
    );

    const activeCountTarget = document.getElementById(
        "xefActiveFilterCount"
    );

    const summaryCountTarget = document.getElementById(
        "xefSummaryFilterCount"
    );

    const filterStatus = document.getElementById(
        "xefFilterStatus"
    );

    const clearButton = document.getElementById(
        "xefClearActiveFilters"
    );

    const selectedFormatTarget = document.getElementById(
        "xefSelectedFormat"
    );

    const quickFilters = Array.from(
        document.querySelectorAll(
            ".xef-quick-filter"
        )
    );

    const exportForms = Array.from(
        document.querySelectorAll(
            "[data-export-form]"
        )
    );

    const ignoredFieldNames = new Set([
        "csrfmiddlewaretoken",
    ]);

    const dateFormatter = new Intl.DateTimeFormat(
        "en-CA",
        {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        }
    );


    function formatDateForInput(date) {
        const year = date.getFullYear();

        const month = String(
            date.getMonth() + 1
        ).padStart(
            2,
            "0"
        );

        const day = String(
            date.getDate()
        ).padStart(
            2,
            "0"
        );

        return `${year}-${month}-${day}`;
    }


    function startOfWeek(date) {
        const result = new Date(date);

        const day = result.getDay();

        const difference = (
            day === 0
                ? -6
                : 1 - day
        );

        result.setDate(
            result.getDate() + difference
        );

        return result;
    }


    function setDateField(
        fieldName,
        value
    ) {
        const input = form.elements.namedItem(
            fieldName
        );

        if (!input) {
            return;
        }

        input.value = value;
        input.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles: true,
                }
            )
        );
    }


    function clearDateFields() {
        setDateField(
            "date_from",
            ""
        );

        setDateField(
            "date_to",
            ""
        );
    }


    function applyQuickPeriod(period) {
        const today = new Date();

        let fromDate = null;
        let toDate = new Date(today);

        switch (period) {
            case "today":
                fromDate = new Date(today);
                break;

            case "week":
                fromDate = startOfWeek(
                    today
                );
                break;

            case "month":
                fromDate = new Date(
                    today.getFullYear(),
                    today.getMonth(),
                    1
                );
                break;

            case "last_30_days":
                fromDate = new Date(
                    today
                );

                fromDate.setDate(
                    fromDate.getDate() - 29
                );
                break;

            case "year":
                fromDate = new Date(
                    today.getFullYear(),
                    0,
                    1
                );
                break;

            case "all":
                clearDateFields();
                setActiveQuickFilter(
                    "all"
                );
                updateActiveFilters();
                return;

            default:
                return;
        }

        setDateField(
            "date_from",
            formatDateForInput(
                fromDate
            )
        );

        setDateField(
            "date_to",
            formatDateForInput(
                toDate
            )
        );

        setActiveQuickFilter(
            period
        );

        updateActiveFilters();
    }


    function setActiveQuickFilter(period) {
        quickFilters.forEach(
            (button) => {
                const isActive = (
                    button.dataset.period
                    === period
                );

                button.classList.toggle(
                    "is-active",
                    isActive
                );

                button.setAttribute(
                    "aria-pressed",
                    isActive
                        ? "true"
                        : "false"
                );
            }
        );
    }


    function getFieldLabel(field) {
        const wrapper = field.closest(
            "[data-filter-field]"
        );

        if (
            wrapper
            && wrapper.dataset.fieldLabel
        ) {
            return wrapper.dataset.fieldLabel;
        }

        const label = form.querySelector(
            `label[for="${CSS.escape(field.id)}"]`
        );

        if (label) {
            return label.textContent.trim();
        }

        return field.name;
    }


    function getFieldDisplayValue(field) {
        if (
            field.type === "checkbox"
            || field.type === "radio"
        ) {
            if (!field.checked) {
                return "";
            }

            const nearbyText = (
                field.closest("label")
                ?.innerText
                ?.trim()
            );

            return nearbyText || "مفعّل";
        }

        if (field.tagName === "SELECT") {
            const selectedOption = (
                field.options[
                    field.selectedIndex
                ]
            );

            if (!selectedOption) {
                return "";
            }

            return (
                selectedOption.textContent
                || ""
            ).trim();
        }

        return (
            field.value
            || ""
        ).trim();
    }


    function isFieldActive(field) {
        if (
            !field.name
            || ignoredFieldNames.has(
                field.name
            )
            || field.disabled
        ) {
            return false;
        }

        if (
            field.type === "checkbox"
            || field.type === "radio"
        ) {
            return field.checked;
        }

        return Boolean(
            (
                field.value
                || ""
            ).trim()
        );
    }


    function clearField(field) {
        if (
            field.type === "checkbox"
            || field.type === "radio"
        ) {
            field.checked = false;
        } else if (
            field.tagName === "SELECT"
        ) {
            field.selectedIndex = 0;
        } else {
            field.value = "";
        }

        field.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles: true,
                }
            )
        );
    }


    function buildActiveFilterChip(field) {
        const chip = document.createElement(
            "span"
        );

        chip.className = (
            "xef-active-filter-chip"
        );

        const label = document.createElement(
            "strong"
        );

        label.textContent = (
            `${getFieldLabel(field)}:`
        );

        const value = document.createElement(
            "span"
        );

        value.textContent = (
            getFieldDisplayValue(field)
        );

        const removeButton = (
            document.createElement(
                "button"
            )
        );

        removeButton.type = "button";

        removeButton.className = (
            "xef-active-filter-remove"
        );

        removeButton.setAttribute(
            "aria-label",
            `إزالة فلتر ${getFieldLabel(field)}`
        );

        removeButton.textContent = "×";

        removeButton.addEventListener(
            "click",
            function () {
                clearField(field);
                updateActiveFilters();
            }
        );

        chip.append(
            label,
            value,
            removeButton
        );

        return chip;
    }


    function updateActiveFilters() {
        const fields = Array.from(
            form.elements
        ).filter(
            (field) => (
                field instanceof
                HTMLElement
            )
        );

        const activeFields = fields.filter(
            isFieldActive
        );

        activeContainer.replaceChildren();

        activeFields.forEach(
            (field) => {
                activeContainer.appendChild(
                    buildActiveFilterChip(
                        field
                    )
                );
            }
        );

        const activeCount = (
            activeFields.length
        );

        activeCountTarget.textContent = (
            String(activeCount)
        );

        summaryCountTarget.textContent = (
            String(activeCount)
        );

        if (activeCount > 0) {
            activeSection.hidden = false;

            filterStatus.textContent = (
                `${activeCount} فلاتر نشطة`
            );

            filterStatus.classList.add(
                "is-active"
            );
        } else {
            activeSection.hidden = true;

            filterStatus.textContent = (
                "لم يتم تطبيق فلاتر"
            );

            filterStatus.classList.remove(
                "is-active"
            );
        }
    }


    function clearAllFilters() {
        const fields = Array.from(
            form.elements
        );

        fields.forEach(
            (field) => {
                if (
                    !(field instanceof HTMLElement)
                    || ignoredFieldNames.has(
                        field.name
                    )
                ) {
                    return;
                }

                clearField(field);
            }
        );

        setActiveQuickFilter(
            ""
        );

        updateActiveFilters();
    }


    function preserveFiltersInActionLinks() {
        const formData = new FormData(
            form
        );

        exportForms.forEach(
            (exportForm) => {
                exportForm
                    .querySelectorAll(
                        "[data-export-field]"
                    )
                    .forEach(
                        (field) => field.remove()
                    );

                for (
                    const [key, value]
                    of formData.entries()
                ) {
                    if (
                        !key
                        || key === "csrfmiddlewaretoken"
                    ) {
                        continue;
                    }

                    const normalized = String(
                        value
                    ).trim();

                    if (!normalized) {
                        continue;
                    }

                    const hiddenField = document.createElement(
                        "input"
                    );
                    hiddenField.type = "hidden";
                    hiddenField.name = key;
                    hiddenField.value = normalized;
                    hiddenField.dataset.exportField = "true";
                    exportForm.appendChild(
                        hiddenField
                    );
                }
            }
        );

        const previewLink = document.querySelector(
            ".xef-preview-action"
        );

        if (previewLink) {
            const query = new URLSearchParams();

            for (
                const [key, value]
                of formData.entries()
            ) {
                if (
                    key === "csrfmiddlewaretoken"
                ) {
                    continue;
                }

                const normalized = String(
                    value
                ).trim();

                if (!normalized) {
                    continue;
                }

                query.append(
                    key,
                    normalized
                );
            }

            const baseUrl = (
                previewLink.dataset.baseUrl
                || previewLink.href.split("?")[0]
            );
            previewLink.dataset.baseUrl = baseUrl;
            previewLink.href = query.toString()
                ? `${baseUrl}?${query.toString()}`
                : baseUrl;
        }
    }


    quickFilters.forEach(
        (button) => {
            button.setAttribute(
                "aria-pressed",
                "false"
            );

            button.addEventListener(
                "click",
                function () {
                    applyQuickPeriod(
                        button.dataset.period
                    );
                }
            );
        }
    );


    form.addEventListener(
        "input",
        function () {
            updateActiveFilters();
            preserveFiltersInActionLinks();
        }
    );


    form.addEventListener(
        "change",
        function () {
            updateActiveFilters();
            preserveFiltersInActionLinks();
        }
    );


    clearButton?.addEventListener(
        "click",
        function () {
            clearAllFilters();
            preserveFiltersInActionLinks();
        }
    );


    exportForms.forEach(
        (form) => {
            const formatName = form.dataset.exportFormat || "غير محدد";
            const submitButton = form.querySelector(
                "button[type='submit']"
            );

            submitButton?.addEventListener(
                "click",
                function () {
                    selectedFormatTarget.textContent = formatName;
                }
            );
        }
    );


    updateActiveFilters();
    preserveFiltersInActionLinks();
})();