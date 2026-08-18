"use strict";

(function () {
    const sectionSwitcher = document.querySelector(
        "[data-section-switcher]"
    );

    const page = document.querySelector(
        "[data-preview-page]"
    );

    if (!page) {
        return;
    }

    const dataUrl = page.dataset.previewDataUrl;

    if (!dataUrl) {
        return;
    }

    const tableHead = document.getElementById(
        "xepTableHead"
    );

    const tableBody = document.getElementById(
        "xepTableBody"
    );

    const searchInput = document.getElementById(
        "xepSearchInput"
    );

    const pageSizeSelect = document.getElementById(
        "xepPageSize"
    );

    const paginationContainer = document.getElementById(
        "xepPagination"
    );

    const loadingState = document.getElementById(
        "xepLoadingState"
    );

    const emptyState = document.getElementById(
        "xepAjaxEmptyState"
    );

    const errorState = document.getElementById(
        "xepAjaxErrorState"
    );

    const tableRegion = document.getElementById(
        "xepTableRegion"
    );

    const totalRecordsTarget = document.getElementById(
        "xepAjaxTotalRecords"
    );

    const filteredRecordsTarget = document.getElementById(
        "xepAjaxFilteredRecords"
    );

    const generatedAtTarget = document.getElementById(
        "xepGeneratedAt"
    );

    const generationTimeTarget = document.getElementById(
        "xepGenerationTime"
    );

    const estimatedSizeTarget = document.getElementById(
        "xepEstimatedSize"
    );

    const startRecordTarget = document.getElementById(
        "xepStartRecord"
    );

    const endRecordTarget = document.getElementById(
        "xepEndRecord"
    );

    const paginationTotalTarget = document.getElementById(
        "xepPaginationTotal"
    );

    const searchClearButton = document.getElementById(
        "xepSearchClear"
    );

    const exportLinks = document.querySelectorAll(
        "[data-export-link]"
    );

    const exportForms = document.querySelectorAll(
        "[data-export-form]"
    );

    const exportSelectionStatus = document.querySelector(
        "[data-export-selection-status]"
    );

    const filterLinks = document.querySelectorAll(
        "[data-filter-link]"
    );

    const columnSelector = document.querySelector(
        "[data-column-selector]"
    );

    let currentPage = 1;
    let currentSortKey = "";
    let currentSortDirection = "asc";
    let currentController = null;
    let searchTimer = null;
    let selectedColumns = Array.from(
        document.querySelectorAll(
            "[data-column-checkbox]:checked"
        )
    ).map(
        (checkbox) => checkbox.value
    );
    let hasColumnSelection = (
        new URL(window.location.href)
        .searchParams.has("selected_columns")
    );


    function escapeHtml(value) {
        return String(
            value ?? ""
        )
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }


    function formatDateTime(value) {
        if (!value) {
            return "—";
        }

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return String(value);
        }

        return new Intl.DateTimeFormat(
            "ar-SA",
            {
                dateStyle: "medium",
                timeStyle: "short",
            }
        ).format(date);
    }


    function formatCellValue(item) {
        const value = item.value;

        if (
            value === null
            || value === undefined
            || value === ""
        ) {
            return `
                <span
                    class="xep-cell-empty"
                    aria-label="قيمة فارغة"
                >
                    —
                </span>
            `;
        }

        if (item.type === "boolean") {
            return value
                ? `
                    <span class="xep-value-badge success">
                        نعم
                    </span>
                `
                : `
                    <span class="xep-value-badge muted">
                        لا
                    </span>
                `;
        }

        if (
            item.type === "date"
            || item.type === "datetime"
        ) {
            return `
                <time
                    class="xep-cell-date"
                    datetime="${escapeHtml(value)}"
                >
                    ${escapeHtml(
                        formatDateTime(value)
                    )}
                </time>
            `;
        }

        if (item.type === "number") {
            return `
                <span class="xep-cell-number">
                    ${escapeHtml(value)}
                </span>
            `;
        }

        return `
            <span
                class="xep-cell-value"
                title="${escapeHtml(value)}"
            >
                ${escapeHtml(value)}
            </span>
        `;
    }


    function renderColumns(columns) {
        const headerCells = columns
            .map(
                (column) => {
                    const isActive = (
                        currentSortKey
                        === column.key
                    );

                    const sortIcon = isActive
                        ? (
                            currentSortDirection
                            === "asc"
                                ? "↑"
                                : "↓"
                        )
                        : "↕";

                    return `
                        <th
                            scope="col"
                            data-sort-key="${escapeHtml(
                                column.key
                            )}"
                            class="
                                xep-sortable-column
                                ${isActive ? "is-sorted" : ""}
                            "
                        >
                            <button
                                type="button"
                                class="xep-sort-button"
                                data-sort-key="${escapeHtml(
                                    column.key
                                )}"
                                aria-label="ترتيب حسب ${escapeHtml(
                                    column.header
                                )}"
                            >
                                <span class="xep-column-copy">
                                    <span class="xep-column-heading">
                                        ${escapeHtml(
                                            column.header
                                        )}
                                    </span>

                                    <small class="xep-column-type">
                                        ${escapeHtml(
                                            column.type
                                            || "text"
                                        )}
                                    </small>
                                </span>

                                <span
                                    class="xep-sort-icon"
                                    aria-hidden="true"
                                >
                                    ${sortIcon}
                                </span>
                            </button>
                        </th>
                    `;
                }
            )
            .join("");

        tableHead.innerHTML = `
            <tr>
                <th scope="col" class="xep-row-number">
                    #
                </th>

                ${headerCells}

                <th
                    scope="col"
                    class="xep-actions-column"
                >
                    الإجراءات
                </th>
            </tr>
        `;
    }


    function buildRowText(row) {
        return row.values
            .map(
                (item) => (
                    item.display_value
                    || item.value
                    || ""
                )
            )
            .join(" | ");
    }


    function renderRows(rows) {
        tableBody.innerHTML = rows
            .map(
                (row) => {
                    const cells = row.values
                        .map(
                            (item) => `
                                <td
                                    data-column-key="${escapeHtml(
                                        item.key
                                    )}"
                                    data-value-type="${escapeHtml(
                                        item.type
                                    )}"
                                >
                                    ${formatCellValue(item)}
                                </td>
                            `
                        )
                        .join("");

                    const recordLink = row.record_url
                        ? `
                            <a
                                href="${escapeHtml(
                                    row.record_url
                                )}"
                                class="xep-row-action"
                                title="فتح السجل الأصلي"
                            >
                                فتح
                            </a>
                        `
                        : "";

                    return `
                        <tr
                            data-record-id="${escapeHtml(
                                row.record_id
                            )}"
                        >
                            <td class="xep-row-number">
                                <span>
                                    ${escapeHtml(
                                        row.number
                                    )}
                                </span>
                            </td>

                            ${cells}

                            <td class="xep-row-actions">
                                <button
                                    type="button"
                                    class="xep-row-action"
                                    data-copy-row
                                    data-row-text="${escapeHtml(
                                        buildRowText(row)
                                    )}"
                                >
                                    نسخ
                                </button>

                                ${recordLink}
                            </td>
                        </tr>
                    `;
                }
            )
            .join("");
    }


    function renderPagination(pagination) {
        const buttons = [];

        buttons.push(`
            <button
                type="button"
                class="xep-page-button"
                data-page="${pagination.previous_page || 1}"
                ${pagination.has_previous ? "" : "disabled"}
            >
                السابق
            </button>
        `);

        const pageWindow = 2;

        const startPage = Math.max(
            1,
            pagination.page - pageWindow
        );

        const endPage = Math.min(
            pagination.total_pages,
            pagination.page + pageWindow
        );

        if (startPage > 1) {
            buttons.push(`
                <button
                    type="button"
                    class="xep-page-button"
                    data-page="1"
                >
                    1
                </button>
            `);

            if (startPage > 2) {
                buttons.push(`
                    <span class="xep-page-ellipsis">
                        …
                    </span>
                `);
            }
        }

        for (
            let pageNumber = startPage;
            pageNumber <= endPage;
            pageNumber += 1
        ) {
            buttons.push(`
                <button
                    type="button"
                    class="
                        xep-page-button
                        ${
                            pageNumber === pagination.page
                                ? "is-active"
                                : ""
                        }
                    "
                    data-page="${pageNumber}"
                    ${
                        pageNumber === pagination.page
                            ? 'aria-current="page"'
                            : ""
                    }
                >
                    ${pageNumber}
                </button>
            `);
        }

        if (endPage < pagination.total_pages) {
            if (
                endPage
                < pagination.total_pages - 1
            ) {
                buttons.push(`
                    <span class="xep-page-ellipsis">
                        …
                    </span>
                `);
            }

            buttons.push(`
                <button
                    type="button"
                    class="xep-page-button"
                    data-page="${pagination.total_pages}"
                >
                    ${pagination.total_pages}
                </button>
            `);
        }

        buttons.push(`
            <button
                type="button"
                class="xep-page-button"
                data-page="${pagination.next_page || pagination.page}"
                ${pagination.has_next ? "" : "disabled"}
            >
                التالي
            </button>
        `);

        paginationContainer.innerHTML = buttons.join("");

        if (startRecordTarget) {
            startRecordTarget.textContent = (
                pagination.start_record
            );
        }

        if (endRecordTarget) {
            endRecordTarget.textContent = (
                pagination.end_record
            );
        }

        if (paginationTotalTarget) {
            paginationTotalTarget.textContent = (
                pagination.total_records
            );
        }
    }


    function showLoading() {
        loadingState.hidden = false;
        errorState.hidden = true;
        emptyState.hidden = true;
        tableRegion.hidden = true;
    }


    function showTable() {
        loadingState.hidden = true;
        errorState.hidden = true;
        emptyState.hidden = true;
        tableRegion.hidden = false;
    }


    function showEmpty() {
        loadingState.hidden = true;
        errorState.hidden = true;
        emptyState.hidden = false;
        tableRegion.hidden = true;
    }


    function showError(message) {
        loadingState.hidden = true;
        emptyState.hidden = true;
        tableRegion.hidden = true;
        errorState.hidden = false;

        const target = errorState.querySelector(
            "[data-error-message]"
        );

        if (target) {
            target.textContent = (
                message
                || "تعذر تحميل بيانات المعاينة."
            );
        }
    }


    function buildRequestUrl() {
        const url = new URL(
            dataUrl,
            window.location.origin
        );

        const currentUrl = new URL(
            window.location.href
        );

        currentUrl.searchParams.forEach(
            (value, key) => {
                if (
                    [
                        "page",
                        "page_size",
                        "search",
                        "sort",
                        "direction",
                    ].includes(key)
                ) {
                    return;
                }

                url.searchParams.append(
                    key,
                    value
                );
            }
        );

        url.searchParams.set(
            "page",
            String(currentPage)
        );

        url.searchParams.set(
            "page_size",
            pageSizeSelect.value
        );

        const searchValue = (
            searchInput.value
            || ""
        ).trim();

        if (searchValue) {
            url.searchParams.set(
                "search",
                searchValue
            );
        }

        if (currentSortKey) {
            url.searchParams.set(
                "sort",
                currentSortKey
            );

            url.searchParams.set(
                "direction",
                currentSortDirection
            );
        }

        return url;
    }


    function updateNavigationUrls() {
        const currentUrl = new URL(
            window.location.href
        );

        exportForms.forEach(
            (exportForm) => {
                exportForm.querySelectorAll(
                    "[data-preview-export-field]"
                ).forEach(
                    (field) => field.remove()
                );

                currentUrl.searchParams.forEach(
                    (value, name) => {
                        const field = document.createElement(
                            "input"
                        );
                        field.type = "hidden";
                        field.name = name;
                        field.value = value;
                        field.dataset.previewExportField = "true";
                        exportForm.appendChild(field);
                    }
                );
            }
        );

        filterLinks.forEach(
            (link) => {
                const filterUrl = new URL(
                    link.href,
                    window.location.origin
                );

                filterUrl.search = currentUrl.search;
                link.href = filterUrl.toString();
            }
        );

        updateExportAvailability();
    }


    function updateExportAvailability() {
        const isDisabled = (
            hasColumnSelection
            && !selectedColumns.length
        );

        exportLinks.forEach(
            (link) => {
                link.setAttribute(
                    "aria-disabled",
                    String(isDisabled)
                );

                link.tabIndex = isDisabled ? -1 : 0;
            }
        );

        if (exportSelectionStatus) {
            exportSelectionStatus.textContent = isDisabled
                ? "حدد عمودًا واحدًا على الأقل لتفعيل التصدير."
                : "";
        }
    }


    function persistColumnSelection() {
        const url = new URL(
            window.location.href
        );

        url.searchParams.delete("selected_columns");

        if (!selectedColumns.length) {
            url.searchParams.append(
                "selected_columns",
                ""
            );
        } else {
            selectedColumns.forEach(
                (columnKey) => {
                    url.searchParams.append(
                        "selected_columns",
                        columnKey
                    );
                }
            );
        }

        window.history.replaceState(
            {},
            "",
            url
        );

        updateNavigationUrls();
    }


    function selectedPayload(payload) {
        if (!hasColumnSelection) {
            return payload;
        }

        const columns = payload.columns.filter(
            (column) => selectedColumns.includes(
                column.key
            )
        );

        const rows = payload.rows.map(
            (row) => ({
                ...row,
                values: row.values.filter(
                    (item) => selectedColumns.includes(
                        item.key
                    )
                ),
            })
        );

        return {
            ...payload,
            columns,
            rows,
        };
    }


    async function loadPreview() {
        if (currentController) {
            currentController.abort();
        }

        currentController = (
            new AbortController()
        );

        showLoading();

        try {
            const response = await fetch(
                buildRequestUrl(),
                {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": (
                            "XMLHttpRequest"
                        ),
                    },
                    signal: (
                        currentController.signal
                    ),
                }
            );

            const payload = await response.json();

            if (
                !response.ok
                || !payload.ok
            ) {
                throw new Error(
                    payload.message
                    || "تعذر تحميل بيانات المعاينة."
                );
            }

            const visiblePayload = selectedPayload(
                payload
            );

            renderColumns(
                visiblePayload.columns
            );

            renderRows(
                visiblePayload.rows
            );

            renderPagination(
                payload.pagination
            );

            if (totalRecordsTarget) {
                totalRecordsTarget.textContent = (
                    payload.summary
                    .total_matching_records
                );
            }

            if (filteredRecordsTarget) {
                filteredRecordsTarget.textContent = (
                    payload.summary
                    .filtered_preview_records
                );
            }

            if (generatedAtTarget) {
                generatedAtTarget.textContent = (
                    formatDateTime(
                        payload.generated_at
                    )
                );
            }

            if (generationTimeTarget) {
                generationTimeTarget.textContent = (
                    `${payload.generation_time_ms} ms`
                );
            }

            if (estimatedSizeTarget) {
                estimatedSizeTarget.textContent = (
                    payload.estimated_size.label
                );
            }

            if (visiblePayload.rows.length) {
                showTable();
            } else {
                showEmpty();
            }
        } catch (error) {
            if (
                error.name === "AbortError"
            ) {
                return;
            }

            console.error(
                "Preview Ajax error:",
                error
            );

            showError(
                error.message
            );
        }
    }


    function copyText(text) {
        if (
            navigator.clipboard
            && window.isSecureContext
        ) {
            return navigator.clipboard.writeText(
                text
            );
        }

        const textarea = document.createElement(
            "textarea"
        );

        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";

        document.body.appendChild(
            textarea
        );

        textarea.select();

        document.execCommand(
            "copy"
        );

        textarea.remove();

        return Promise.resolve();
    }


    tableHead.addEventListener(
        "click",
        function (event) {
            const button = event.target.closest(
                "[data-sort-key]"
            );

            if (!button) {
                return;
            }

            const sortKey = (
                button.dataset.sortKey
            );

            if (
                currentSortKey
                === sortKey
            ) {
                currentSortDirection = (
                    currentSortDirection
                    === "asc"
                        ? "desc"
                        : "asc"
                );
            } else {
                currentSortKey = sortKey;
                currentSortDirection = "asc";
            }

            currentPage = 1;

            loadPreview();
        }
    );


    tableBody.addEventListener(
        "click",
        async function (event) {
            const copyButton = event.target.closest(
                "[data-copy-row]"
            );

            if (!copyButton) {
                return;
            }

            const originalText = (
                copyButton.textContent
            );

            try {
                await copyText(
                    copyButton.dataset.rowText
                    || ""
                );

                copyButton.textContent = (
                    "تم النسخ"
                );

                setTimeout(
                    function () {
                        copyButton.textContent = (
                            originalText
                        );
                    },
                    1500
                );
            } catch (error) {
                console.error(
                    "Copy failed:",
                    error
                );

                copyButton.textContent = (
                    "فشل النسخ"
                );
            }
        }
    );


    paginationContainer.addEventListener(
        "click",
        function (event) {
            const button = event.target.closest(
                "[data-page]"
            );

            if (
                !button
                || button.disabled
            ) {
                return;
            }

            currentPage = Number(
                button.dataset.page
            );

            loadPreview();
        }
    );


    pageSizeSelect.addEventListener(
        "change",
        function () {
            currentPage = 1;
            loadPreview();
        }
    );


    searchInput.addEventListener(
        "input",
        function () {
            window.clearTimeout(
                searchTimer
            );

            searchTimer = window.setTimeout(
                function () {
                    currentPage = 1;
                    loadPreview();
                },
                350
            );
        }
    );


    searchClearButton?.addEventListener(
        "click",
        function () {
            searchInput.value = "";
            currentPage = 1;
            loadPreview();
            searchInput.focus();
        }
    );


    sectionSwitcher?.addEventListener(
        "click",
        function (event) {
            const button = event.target.closest(
                "[data-section-value]"
            );

            if (!button) {
                return;
            }

            const sectionValue = button.dataset.sectionValue;
            const url = new URL(window.location.href);

            if (sectionValue === "all") {
                url.searchParams.delete("section");
                url.searchParams.delete("operational_section");
            } else {
                url.searchParams.set("section", sectionValue);

                if (url.searchParams.has("operational_section")) {
                    url.searchParams.set("operational_section", sectionValue);
                }
            }

            ["page", "search", "sort", "direction"].forEach(
                (parameter) => url.searchParams.delete(parameter)
            );

            window.history.replaceState({}, "", url);

            sectionSwitcher.querySelectorAll(
                "[data-section-value]"
            ).forEach(
                (sectionButton) => {
                    sectionButton.setAttribute(
                        "aria-pressed",
                        String(
                            sectionButton === button
                        )
                    );
                }
            );

            currentPage = 1;
            updateNavigationUrls();
            loadPreview();
        }
    );


    columnSelector?.addEventListener(
        "change",
        function (event) {
            const checkbox = event.target.closest(
                "[data-column-checkbox]"
            );

            if (!checkbox) {
                return;
            }

            selectedColumns = Array.from(
                columnSelector.querySelectorAll(
                    "[data-column-checkbox]:checked"
                )
            ).map(
                (selectedCheckbox) => selectedCheckbox.value
            );

            hasColumnSelection = true;
            persistColumnSelection();
            currentPage = 1;
            loadPreview();
        }
    );


    columnSelector?.addEventListener(
        "click",
        function (event) {
            const selectAll = event.target.closest(
                "[data-select-all-columns]"
            );

            const clearAll = event.target.closest(
                "[data-clear-all-columns]"
            );

            if (!selectAll && !clearAll) {
                return;
            }

            const checked = Boolean(selectAll);

            columnSelector.querySelectorAll(
                "[data-column-checkbox]"
            ).forEach(
                (checkbox) => {
                    checkbox.checked = checked;
                }
            );

            selectedColumns = Array.from(
                columnSelector.querySelectorAll(
                    "[data-column-checkbox]:checked"
                )
            ).map(
                (checkbox) => checkbox.value
            );

            hasColumnSelection = true;
            persistColumnSelection();
            currentPage = 1;
            loadPreview();
        }
    );


    exportLinks.forEach(
        (link) => {
            link.addEventListener(
                "click",
                function (event) {
                    if (
                        link.getAttribute(
                            "aria-disabled"
                        ) === "true"
                    ) {
                        event.preventDefault();
                    }
                }
            );
        }
    );


    updateNavigationUrls();
    loadPreview();
})();
