/* =========================================================
   منصة أبواب — مدير AJAX الموحد
   الملف: static/js/ajax.js
   الإصدار: 2026.07.28
========================================================= */

(function () {
    "use strict";

    const AjaxManager = {
        config: {
            timeout: 30000,
            retryCount: 1,
            retryDelay: 700,
            searchDelay: 350,
            csrfCookieName: "csrftoken",
        },

        state: {
            activeRequests: new Map(),
            searchTimers: new WeakMap(),
        },

        init() {
            this.initAjaxForms();
            this.initAjaxLinks();
            this.initAjaxButtons();
            this.initLiveSearch();
            this.initAjaxPagination();
            this.initAjaxFilters();
            this.initAutoRefresh();

            this.dispatch(
                "abwaab:ajax-ready",
                {
                    manager: this,
                }
            );
        },

        /* =====================================================
           الأدوات العامة
        ===================================================== */

        dispatch(name, detail = {}) {
            document.dispatchEvent(
                new CustomEvent(
                    name,
                    {
                        detail,
                    }
                )
            );
        },

        qs(selector, root = document) {
            return root.querySelector(
                selector
            );
        },

        qsa(selector, root = document) {
            return Array.from(
                root.querySelectorAll(
                    selector
                )
            );
        },

        getCookie(name) {
            if (
                window.AbwaabApp &&
                typeof window.AbwaabApp.getCookie ===
                    "function"
            ) {
                return window.AbwaabApp.getCookie(
                    name
                );
            }

            const cookie = document.cookie
                .split(";")
                .map((item) => {
                    return item.trim();
                })
                .find((item) => {
                    return item.startsWith(
                        `${name}=`
                    );
                });

            if (!cookie) {
                return null;
            }

            return decodeURIComponent(
                cookie
                    .split("=")
                    .slice(1)
                    .join("=")
            );
        },

        getCsrfToken() {
            const input =
                document.querySelector(
                    'input[name="csrfmiddlewaretoken"]'
                );

            return (
                input?.value ||
                this.getCookie(
                    this.config.csrfCookieName
                )
            );
        },

        sleep(milliseconds) {
            return new Promise(
                (resolve) => {
                    window.setTimeout(
                        resolve,
                        milliseconds
                    );
                }
            );
        },

        createRequestId() {
            return [
                Date.now(),
                Math.random()
                    .toString(36)
                    .slice(2),
            ].join("-");
        },

        /* =====================================================
           قراءة استجابة الخادم
        ===================================================== */

        async parseResponse(response) {
            const contentType =
                response.headers.get(
                    "content-type"
                ) || "";

            if (
                contentType.includes(
                    "application/json"
                )
            ) {
                return response.json();
            }

            const text =
                await response.text();

            const normalized =
                text
                    .trim()
                    .toLowerCase();

            if (
                normalized.startsWith(
                    "<!doctype"
                ) ||
                normalized.startsWith(
                    "<html"
                )
            ) {
                const error =
                    new Error(
                        "أعاد الخادم صفحة HTML بدلًا من بيانات JSON."
                    );

                error.code =
                    "HTML_RESPONSE";

                error.status =
                    response.status;

                error.responseText =
                    text;

                throw error;
            }

            return {
                success: response.ok,
                message: text,
                html: text,
            };
        },

        /* =====================================================
           معالجة الأخطاء
        ===================================================== */

        normalizeError(error) {
            if (
                error?.name ===
                "AbortError"
            ) {
                return {
                    message:
                        "انتهت مهلة الاتصال بالخادم.",
                    type: "warning",
                    code: "TIMEOUT",
                };
            }

            if (
                error?.code ===
                "HTML_RESPONSE"
            ) {
                return {
                    message:
                        "أعاد الخادم صفحة HTML. تحقق من تسجيل الدخول أو رابط الطلب أو سجل أخطاء Django.",
                    type: "danger",
                    code: error.code,
                };
            }

            if (
                error?.status === 400
            ) {
                return {
                    message:
                        error?.message ||
                        "البيانات المرسلة غير صحيحة.",
                    type: "warning",
                    code: "BAD_REQUEST",
                };
            }

            if (
                error?.status === 401
            ) {
                return {
                    message:
                        "انتهت جلسة الدخول. أعد تسجيل الدخول.",
                    type: "warning",
                    code: "UNAUTHORIZED",
                };
            }

            if (
                error?.status === 403
            ) {
                return {
                    message:
                        "ليس لديك صلاحية لتنفيذ هذه العملية.",
                    type: "danger",
                    code: "FORBIDDEN",
                };
            }

            if (
                error?.status === 404
            ) {
                return {
                    message:
                        "لم يتم العثور على المسار المطلوب.",
                    type: "danger",
                    code: "NOT_FOUND",
                };
            }

            if (
                error?.status === 409
            ) {
                return {
                    message:
                        error?.message ||
                        "تعذر تنفيذ العملية بسبب تعارض في البيانات.",
                    type: "warning",
                    code: "CONFLICT",
                };
            }

            if (
                error?.status === 422
            ) {
                return {
                    message:
                        error?.message ||
                        "تعذر التحقق من البيانات المدخلة.",
                    type: "warning",
                    code: "VALIDATION_ERROR",
                };
            }

            if (
                error?.status >= 500
            ) {
                return {
                    message:
                        "حدث خطأ داخلي في الخادم. راجع سجل Django.",
                    type: "danger",
                    code: "SERVER_ERROR",
                };
            }

            return {
                message:
                    error?.message ||
                    "تعذر تنفيذ العملية بسبب خطأ غير متوقع.",
                type: "danger",
                code:
                    error?.code ||
                    "UNKNOWN",
            };
        },

        showError(error, options = {}) {
            const normalized =
                this.normalizeError(
                    error
                );

            const message =
                options.message ||
                normalized.message;

            if (
                window.showToast &&
                options.toast !== false
            ) {
                window.showToast(
                    message,
                    {
                        type:
                            options.type ||
                            normalized.type,
                    }
                );
            }

            console.error(
                "AJAX Error:",
                error
            );

            return normalized;
        },

        /* =====================================================
           تنفيذ الطلب الأساسي
        ===================================================== */

        async request(url, options = {}) {
            const {
                method = "GET",
                headers = {},
                body = null,
                timeout =
                    this.config.timeout,
                retries =
                    this.config.retryCount,
                retryDelay =
                    this.config.retryDelay,
                loading = false,
                loadingTitle =
                    "جارٍ تنفيذ العملية",
                loadingMessage =
                    "يرجى الانتظار قليلًا...",
                signal = null,
                requestKey = null,
            } = options;

            const requestId =
                requestKey ||
                this.createRequestId();

            if (
                requestKey &&
                this.state.activeRequests.has(
                    requestKey
                )
            ) {
                this.state.activeRequests
                    .get(requestKey)
                    .abort();
            }

            const controller =
                new AbortController();

            this.state.activeRequests.set(
                requestId,
                controller
            );

            if (
                loading &&
                window.showAppLoading
            ) {
                window.showAppLoading({
                    title:
                        loadingTitle,

                    message:
                        loadingMessage,
                });
            }

            const requestHeaders =
                new Headers(
                    headers
                );

            requestHeaders.set(
                "X-Requested-With",
                "XMLHttpRequest"
            );

            if (
                ![
                    "GET",
                    "HEAD",
                    "OPTIONS",
                    "TRACE",
                ].includes(
                    method.toUpperCase()
                )
            ) {
                const csrfToken =
                    this.getCsrfToken();

                if (csrfToken) {
                    requestHeaders.set(
                        "X-CSRFToken",
                        csrfToken
                    );
                }
            }

            let requestBody =
                body;

            if (
                body &&
                !(body instanceof FormData) &&
                typeof body ===
                    "object"
            ) {
                if (
                    !requestHeaders.has(
                        "Content-Type"
                    )
                ) {
                    requestHeaders.set(
                        "Content-Type",
                        "application/json"
                    );
                }

                requestBody =
                    JSON.stringify(
                        body
                    );
            }

            const execute =
                async (
                    attempt = 0
                ) => {
                    let timeoutId =
                        null;

                    try {
                        timeoutId =
                            window.setTimeout(
                                () => {
                                    controller.abort();
                                },
                                timeout
                            );

                        const response =
                            await fetch(
                                url,
                                {
                                    method:
                                        method.toUpperCase(),

                                    headers:
                                        requestHeaders,

                                    body:
                                        requestBody,

                                    credentials:
                                        "same-origin",

                                    signal:
                                        signal ||
                                        controller.signal,
                                }
                            );

                        window.clearTimeout(
                            timeoutId
                        );

                        const data =
                            await this.parseResponse(
                                response
                            );

                        if (
                            !response.ok
                        ) {
                            const error =
                                new Error(
                                    data?.message ||
                                    data?.error ||
                                    `HTTP ${response.status}`
                                );

                            error.status =
                                response.status;

                            error.data =
                                data;

                            throw error;
                        }

                        return {
                            response,
                            data,
                        };
                    } catch (error) {
                        window.clearTimeout(
                            timeoutId
                        );

                        const retryable =
                            error.name !==
                                "AbortError" &&
                            (
                                !error.status ||
                                error.status >=
                                    500
                            );

                        if (
                            retryable &&
                            attempt < retries
                        ) {
                            await this.sleep(
                                retryDelay *
                                (
                                    attempt +
                                    1
                                )
                            );

                            return execute(
                                attempt + 1
                            );
                        }

                        throw error;
                    }
                };

            try {
                const result =
                    await execute();

                this.dispatch(
                    "abwaab:ajax-success",
                    {
                        url,
                        method,
                        result,
                    }
                );

                return result;
            } catch (error) {
                this.dispatch(
                    "abwaab:ajax-error",
                    {
                        url,
                        method,
                        error,
                    }
                );

                throw error;
            } finally {
                this.state.activeRequests.delete(
                    requestId
                );

                if (
                    loading &&
                    window.hideAppLoading
                ) {
                    window.hideAppLoading();
                }
            }
        },

        /* =====================================================
           اختصارات الطلبات
        ===================================================== */

        get(url, options = {}) {
            return this.request(
                url,
                {
                    ...options,
                    method: "GET",
                }
            );
        },

        post(
            url,
            body = null,
            options = {}
        ) {
            return this.request(
                url,
                {
                    ...options,
                    method: "POST",
                    body,
                }
            );
        },

        put(
            url,
            body = null,
            options = {}
        ) {
            return this.request(
                url,
                {
                    ...options,
                    method: "PUT",
                    body,
                }
            );
        },

        patch(
            url,
            body = null,
            options = {}
        ) {
            return this.request(
                url,
                {
                    ...options,
                    method: "PATCH",
                    body,
                }
            );
        },

        delete(
            url,
            body = null,
            options = {}
        ) {
            return this.request(
                url,
                {
                    ...options,
                    method: "DELETE",
                    body,
                }
            );
        },

        /* =====================================================
           تهيئة نماذج AJAX
        ===================================================== */

        initAjaxForms(
            root = document
        ) {
            this.qsa(
                'form[data-ajax="true"]',
                root
            ).forEach(
                (form) => {
                    if (
                        form.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    form.dataset
                        .ajaxInitialized =
                        "true";

                    form.addEventListener(
                        "submit",
                        async (
                            event
                        ) => {
                            event.preventDefault();

                            if (
                                !form.checkValidity()
                            ) {
                                form.reportValidity();

                                return;
                            }

                            await this.submitForm(
                                form
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           إرسال النموذج
        ===================================================== */

        async submitForm(form) {
            const buttons =
                form.querySelectorAll(
                    `
                        button[type="submit"],
                        input[type="submit"]
                    `
                );

            const formData =
                new FormData(
                    form
                );

            const method =
                (
                    form.getAttribute(
                        "method"
                    ) ||
                    "POST"
                ).toUpperCase();

            const url =
                form.getAttribute(
                    "action"
                ) ||
                window.location.href;

            const targetSelector =
                form.dataset
                    .ajaxTarget;

            buttons.forEach(
                (button) => {
                    button.disabled =
                        true;

                    button.classList.add(
                        "is-loading"
                    );
                }
            );

            this.clearFormErrors(
                form
            );

            try {
                const {
                    data,
                } =
                    await this.request(
                        url,
                        {
                            method,
                            body:
                                formData,

                            loading:
                                form.dataset
                                    .ajaxLoading ===
                                "true",

                            loadingTitle:
                                form.dataset
                                    .loadingTitle ||
                                "جارٍ حفظ البيانات",

                            loadingMessage:
                                form.dataset
                                    .loadingMessage ||
                                "يتم الآن إرسال البيانات...",
                        }
                    );

                if (
                    data.success ===
                    false
                ) {
                    this.handleValidationErrors(
                        form,
                        data.errors ||
                        {}
                    );

                    if (
                        data.message
                    ) {
                        window.showToast?.(
                            data.message,
                            {
                                type:
                                    "danger",
                            }
                        );
                    }

                    return data;
                }

                if (
                    targetSelector &&
                    data.html
                ) {
                    this.updateTarget(
                        targetSelector,
                        data.html
                    );
                }

                if (
                    data.redirect_url ||
                    data.redirect
                ) {
                    window.location.href =
                        data.redirect_url ||
                        data.redirect;

                    return data;
                }

                if (
                    form.dataset
                        .resetOnSuccess ===
                    "true"
                ) {
                    form.reset();
                }

                if (
                    form.dataset
                        .closeModalOnSuccess ===
                        "true" &&
                    window.closeAppModal
                ) {
                    const modal =
                        form.closest(
                            `
                                .app-modal,
                                .modal-backdrop
                            `
                        );

                    if (modal) {
                        window.closeAppModal(
                            modal
                        );
                    }
                }

                window.showToast?.(
                    data.message ||
                    "تم حفظ البيانات بنجاح.",
                    {
                        type:
                            "success",
                    }
                );

                this.dispatch(
                    "abwaab:form-success",
                    {
                        form,
                        data,
                    }
                );

                return data;
            } catch (error) {
                if (
                    error?.data
                        ?.errors
                ) {
                    this.handleValidationErrors(
                        form,
                        error.data.errors
                    );
                }

                this.showError(
                    error
                );

                this.dispatch(
                    "abwaab:form-error",
                    {
                        form,
                        error,
                    }
                );

                return null;
            } finally {
                buttons.forEach(
                    (button) => {
                        button.disabled =
                            false;

                        button.classList.remove(
                            "is-loading"
                        );
                    }
                );
            }
        },

        /* =====================================================
           أخطاء النماذج
        ===================================================== */

        clearFormErrors(form) {
            this.qsa(
                ".ajax-field-error",
                form
            ).forEach(
                (element) => {
                    element.remove();
                }
            );

            this.qsa(
                ".is-error",
                form
            ).forEach(
                (element) => {
                    element.classList.remove(
                        "is-error"
                    );
                }
            );
        },

        handleValidationErrors(
            form,
            errors
        ) {
            Object.entries(
                errors
            ).forEach(
                (
                    [
                        fieldName,
                        messages,
                    ]
                ) => {
                    const escapedName =
                        window.CSS
                            ?.escape
                            ? CSS.escape(
                                fieldName
                            )
                            : fieldName;

                    const field =
                        form.querySelector(
                            `[name="${escapedName}"]`
                        );

                    if (!field) {
                        return;
                    }

                    const wrapper =
                        field.closest(
                            `
                                .app-form-field,
                                .form-field
                            `
                        ) ||
                        field.parentElement;

                    wrapper?.classList.add(
                        "is-error"
                    );

                    const errorElement =
                        document.createElement(
                            "div"
                        );

                    errorElement.className =
                        "app-field-message ajax-field-error";

                    errorElement.textContent =
                        Array.isArray(
                            messages
                        )
                            ? messages.join(
                                " "
                            )
                            : String(
                                messages
                            );

                    wrapper?.appendChild(
                        errorElement
                    );
                }
            );

            form.querySelector(
                `
                    .is-error input,
                    .is-error select,
                    .is-error textarea
                `
            )?.focus();
        },

        /* =====================================================
           روابط AJAX
        ===================================================== */

        initAjaxLinks(
            root = document
        ) {
            this.qsa(
                'a[data-ajax-link="true"]',
                root
            ).forEach(
                (link) => {
                    if (
                        link.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    link.dataset
                        .ajaxInitialized =
                        "true";

                    link.addEventListener(
                        "click",
                        async (
                            event
                        ) => {
                            event.preventDefault();

                            await this.handleAjaxElement(
                                link,
                                link.href,
                                "GET"
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           أزرار AJAX
        ===================================================== */

        initAjaxButtons(
            root = document
        ) {
            this.qsa(
                "[data-ajax-url]",
                root
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .ajaxInitialized =
                        "true";

                    button.addEventListener(
                        "click",
                        async (
                            event
                        ) => {
                            event.preventDefault();

                            const method =
                                (
                                    button.dataset
                                        .ajaxMethod ||
                                    "POST"
                                ).toUpperCase();

                            await this.handleAjaxElement(
                                button,
                                button.dataset
                                    .ajaxUrl,
                                method
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           تنفيذ طلب زر أو رابط
        ===================================================== */

        async handleAjaxElement(
            element,
            url,
            method
        ) {
            if (!url) {
                return;
            }

            if (
                element.dataset
                    .confirm &&
                window.confirmAppAction
            ) {
                const approved =
                    await window.confirmAppAction({
                        title:
                            element.dataset
                                .confirmTitle ||
                            "تأكيد العملية",

                        message:
                            element.dataset
                                .confirm,

                        type:
                            element.dataset
                                .confirmType ||
                            "danger",
                    });

                if (!approved) {
                    return;
                }
            }

            element.disabled =
                true;

            element.classList.add(
                "is-loading"
            );

            let body =
                null;

            if (
                element.dataset
                    .ajaxData
            ) {
                try {
                    body =
                        JSON.parse(
                            element.dataset
                                .ajaxData
                        );
                } catch (error) {
                    console.error(
                        "Invalid data-ajax-data JSON",
                        error
                    );
                }
            }

            try {
                const {
                    data,
                } =
                    await this.request(
                        url,
                        {
                            method,
                            body,

                            loading:
                                element.dataset
                                    .ajaxLoading ===
                                "true",
                        }
                    );

                if (
                    data.redirect_url ||
                    data.redirect
                ) {
                    window.location.href =
                        data.redirect_url ||
                        data.redirect;

                    return;
                }

                if (
                    element.dataset
                        .ajaxTarget &&
                    data.html
                ) {
                    this.updateTarget(
                        element.dataset
                            .ajaxTarget,
                        data.html
                    );
                }

                if (
                    element.dataset
                        .removeTarget &&
                    data.success !==
                        false
                ) {
                    document
                        .querySelector(
                            element.dataset
                                .removeTarget
                        )
                        ?.remove();
                }

                if (
                    element.dataset
                        .reload ===
                    "true"
                ) {
                    window.location.reload();

                    return;
                }

                window.showToast?.(
                    data.message ||
                    "تم تنفيذ العملية بنجاح.",
                    {
                        type:
                            data.success ===
                            false
                                ? "danger"
                                : "success",
                    }
                );

                this.dispatch(
                    "abwaab:element-success",
                    {
                        element,
                        data,
                    }
                );
            } catch (error) {
                this.showError(
                    error
                );
            } finally {
                element.disabled =
                    false;

                element.classList.remove(
                    "is-loading"
                );
            }
        },

        /* =====================================================
           تحديث المحتوى
        ===================================================== */

        updateTarget(
            selector,
            html
        ) {
            const target =
                document.querySelector(
                    selector
                );

            if (!target) {
                return false;
            }

            target.innerHTML =
                html;

            this.reinitialize(
                target
            );

            this.dispatch(
                "abwaab:target-updated",
                {
                    target,
                    selector,
                }
            );

            return true;
        },

        replaceTarget(
            selector,
            html
        ) {
            const target =
                document.querySelector(
                    selector
                );

            if (!target) {
                return false;
            }

            const template =
                document.createElement(
                    "template"
                );

            template.innerHTML =
                html.trim();

            const replacement =
                template.content
                    .firstElementChild;

            if (!replacement) {
                return false;
            }

            target.replaceWith(
                replacement
            );

            this.reinitialize(
                replacement
            );

            return true;
        },

        /* =====================================================
           إعادة تهيئة العناصر الجديدة
        ===================================================== */

        reinitialize(
            root = document
        ) {
            this.initAjaxForms(
                root
            );

            this.initAjaxLinks(
                root
            );

            this.initAjaxButtons(
                root
            );

            this.initLiveSearch(
                root
            );

            this.initAjaxPagination(
                root
            );

            this.initAjaxFilters(
                root
            );

            window.AbwaabApp
                ?.initAlerts
                ?.();

            window.AbwaabApp
                ?.initAccordions
                ?.();

            window.AbwaabApp
                ?.initFileInputs
                ?.();

            window.AbwaabApp
                ?.initPasswordToggles
                ?.();
        },

        /* =====================================================
           البحث اللحظي
        ===================================================== */

        initLiveSearch(
            root = document
        ) {
            this.qsa(
                "[data-live-search]",
                root
            ).forEach(
                (input) => {
                    if (
                        input.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    input.dataset
                        .ajaxInitialized =
                        "true";

                    input.addEventListener(
                        "input",
                        () => {
                            window.clearTimeout(
                                this.state
                                    .searchTimers
                                    .get(
                                        input
                                    )
                            );

                            const timer =
                                window.setTimeout(
                                    () => {
                                        this.performLiveSearch(
                                            input
                                        );
                                    },

                                    Number(
                                        input.dataset
                                            .searchDelay
                                    ) ||
                                    this.config
                                        .searchDelay
                                );

                            this.state
                                .searchTimers
                                .set(
                                    input,
                                    timer
                                );
                        }
                    );
                }
            );
        },

        async performLiveSearch(
            input
        ) {
            const url =
                input.dataset
                    .liveSearch;

            const target =
                input.dataset
                    .searchTarget;

            if (
                !url ||
                !target
            ) {
                return;
            }

            const requestUrl =
                new URL(
                    url,
                    window.location.origin
                );

            requestUrl
                .searchParams
                .set(
                    input.dataset
                        .searchParam ||
                    "q",

                    input.value.trim()
                );

            try {
                const {
                    data,
                } =
                    await this.get(
                        requestUrl.toString(),
                        {
                            requestKey:
                                `search:${target}`,
                        }
                    );

                if (
                    data.html
                ) {
                    this.updateTarget(
                        target,
                        data.html
                    );
                }
            } catch (error) {
                if (
                    error.name !==
                    "AbortError"
                ) {
                    this.showError(
                        error,
                        {
                            toast:
                                false,
                        }
                    );
                }
            }
        },

        /* =====================================================
           Pagination عبر AJAX
        ===================================================== */

        initAjaxPagination(
            root = document
        ) {
            this.qsa(
                "[data-ajax-pagination] a",
                root
            ).forEach(
                (link) => {
                    if (
                        link.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    link.dataset
                        .ajaxInitialized =
                        "true";

                    link.addEventListener(
                        "click",
                        async (
                            event
                        ) => {
                            event.preventDefault();

                            const container =
                                link.closest(
                                    "[data-ajax-pagination]"
                                );

                            const target =
                                container
                                    ?.dataset
                                    .ajaxPagination;

                            if (
                                !target
                            ) {
                                return;
                            }

                            try {
                                const {
                                    data,
                                } =
                                    await this.get(
                                        link.href,
                                        {
                                            loading:
                                                true,

                                            loadingTitle:
                                                "جارٍ تحميل الصفحة",
                                        }
                                    );

                                if (
                                    data.html
                                ) {
                                    this.updateTarget(
                                        target,
                                        data.html
                                    );

                                    document
                                        .querySelector(
                                            target
                                        )
                                        ?.scrollIntoView({
                                            behavior:
                                                "smooth",

                                            block:
                                                "start",
                                        });
                                }
                            } catch (
                                error
                            ) {
                                this.showError(
                                    error
                                );
                            }
                        }
                    );
                }
            );
        },

        /* =====================================================
           فلاتر AJAX
        ===================================================== */

        initAjaxFilters(
            root = document
        ) {
            this.qsa(
                'form[data-ajax-filter="true"]',
                root
            ).forEach(
                (form) => {
                    if (
                        form.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    form.dataset
                        .ajaxInitialized =
                        "true";

                    const submitFilter =
                        async () => {
                            const target =
                                form.dataset
                                    .ajaxTarget;

                            if (
                                !target
                            ) {
                                return;
                            }

                            const url =
                                new URL(
                                    form.action ||
                                    window.location.href
                                );

                            url.search =
                                new URLSearchParams(
                                    new FormData(
                                        form
                                    )
                                ).toString();

                            try {
                                const {
                                    data,
                                } =
                                    await this.get(
                                        url.toString(),
                                        {
                                            requestKey:
                                                `filter:${target}`,
                                        }
                                    );

                                if (
                                    data.html
                                ) {
                                    this.updateTarget(
                                        target,
                                        data.html
                                    );
                                }

                                if (
                                    form.dataset
                                        .updateUrl ===
                                    "true"
                                ) {
                                    window.history
                                        .replaceState(
                                            {},
                                            "",
                                            url.toString()
                                        );
                                }
                            } catch (
                                error
                            ) {
                                if (
                                    error.name !==
                                    "AbortError"
                                ) {
                                    this.showError(
                                        error
                                    );
                                }
                            }
                        };

                    form.addEventListener(
                        "submit",
                        (
                            event
                        ) => {
                            event.preventDefault();

                            submitFilter();
                        }
                    );

                    this.qsa(
                        '[data-filter-auto="true"]',
                        form
                    ).forEach(
                        (field) => {
                            field.addEventListener(
                                field.matches(
                                    "select"
                                )
                                    ? "change"
                                    : "input",

                                () => {
                                    window.clearTimeout(
                                        field._filterTimer
                                    );

                                    field._filterTimer =
                                        window.setTimeout(
                                            submitFilter,

                                            Number(
                                                field.dataset
                                                    .filterDelay
                                            ) ||
                                            this.config
                                                .searchDelay
                                        );
                                }
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           التحديث التلقائي
        ===================================================== */

        initAutoRefresh(
            root = document
        ) {
            this.qsa(
                "[data-auto-refresh-url]",
                root
            ).forEach(
                (element) => {
                    if (
                        element.dataset
                            .ajaxInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    element.dataset
                        .ajaxInitialized =
                        "true";

                    const url =
                        element.dataset
                            .autoRefreshUrl;

                    const interval =
                        Math.max(
                            5000,

                            Number(
                                element.dataset
                                    .autoRefreshInterval
                            ) ||
                            30000
                        );

                    const refresh =
                        async () => {
                            if (
                                document.hidden
                            ) {
                                return;
                            }

                            try {
                                const {
                                    data,
                                } =
                                    await this.get(
                                        url,
                                        {
                                            requestKey:
                                                `refresh:${url}`,
                                        }
                                    );

                                if (
                                    data.html
                                ) {
                                    element.innerHTML =
                                        data.html;

                                    this.reinitialize(
                                        element
                                    );
                                }

                                this.dispatch(
                                    "abwaab:auto-refresh",
                                    {
                                        element,
                                        data,
                                    }
                                );
                            } catch (
                                error
                            ) {
                                if (
                                    error.name !==
                                    "AbortError"
                                ) {
                                    console.error(
                                        "Auto refresh error:",
                                        error
                                    );
                                }
                            }
                        };

                    element._refreshTimer =
                        window.setInterval(
                            refresh,
                            interval
                        );
                }
            );
        },
    };

    /* =========================================================
       إتاحة المدير عالميًا
    ========================================================= */

    window.AbwaabAjax =
        AjaxManager;

    window.ajaxRequest =
        function (
            url,
            options
        ) {
            return AjaxManager.request(
                url,
                options
            );
        };

    window.ajaxGet =
        function (
            url,
            options
        ) {
            return AjaxManager.get(
                url,
                options
            );
        };

    window.ajaxPost =
        function (
            url,
            body,
            options
        ) {
            return AjaxManager.post(
                url,
                body,
                options
            );
        };

    window.ajaxPut =
        function (
            url,
            body,
            options
        ) {
            return AjaxManager.put(
                url,
                body,
                options
            );
        };

    window.ajaxPatch =
        function (
            url,
            body,
            options
        ) {
            return AjaxManager.patch(
                url,
                body,
                options
            );
        };

    window.ajaxDelete =
        function (
            url,
            body,
            options
        ) {
            return AjaxManager.delete(
                url,
                body,
                options
            );
        };

    /* =========================================================
       تشغيل مدير AJAX
    ========================================================= */

    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                AjaxManager.init();
            }
        );
    } else {
        AjaxManager.init();
    }
})();