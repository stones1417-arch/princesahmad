/* =========================================================
   منصة أبواب — JavaScript العام
   الملف: static/js/app.js
   الإصدار: 2026.07.28
========================================================= */

(function () {
    "use strict";

    const App = {
        config: {
            alertTimeout: 6500,
            toastTimeout: 5000,
            loadingDelay: 120,
            themeStorageKey: "abwaab-theme",
            legacyThemeStorageKey: "theme",
            defaultTheme: "light",
        },

        state: {
            loadingTimer: null,
            activeDropdown: null,
            initialized: false,
        },

        init() {
            if (
                this.state.initialized
            ) {
                return;
            }

            this.state.initialized =
                true;

            this.cacheElements();
            this.initTheme();
            this.initAlerts();
            this.initDropdowns();
            this.initAccordions();
            this.initDrawers();
            this.initFileInputs();
            this.initPasswordToggles();
            this.initAutoSubmit();
            this.initGlobalShortcuts();
            this.initForms();
            this.initExternalLinks();
            this.dispatchReady();
        },

        cacheElements() {
            this.elements = {
                body:
                    document.body,

                html:
                    document.documentElement,

                loadingOverlay:
                    document.getElementById(
                        "globalLoadingOverlay"
                    ),

                loadingTitle:
                    document.getElementById(
                        "globalLoadingTitle"
                    ),

                loadingMessage:
                    document.getElementById(
                        "globalLoadingMessage"
                    ),

                toastContainer:
                    document.getElementById(
                        "appToastContainer"
                    ),
            };
        },

        /* =====================================================
           الأدوات العامة
        ===================================================== */

        qs(
            selector,
            root = document
        ) {
            return root.querySelector(
                selector
            );
        },

        qsa(
            selector,
            root = document
        ) {
            return Array.from(
                root.querySelectorAll(
                    selector
                )
            );
        },

        isVisible(element) {
            if (!element) {
                return false;
            }

            return Boolean(
                element.offsetWidth ||
                element.offsetHeight ||
                element
                    .getClientRects()
                    .length
            );
        },

        debounce(
            callback,
            delay = 250
        ) {
            let timer =
                null;

            return function (...args) {
                window.clearTimeout(
                    timer
                );

                timer =
                    window.setTimeout(
                        () => {
                            callback.apply(
                                this,
                                args
                            );
                        },
                        delay
                    );
            };
        },

        escapeHtml(value) {
            const div =
                document.createElement(
                    "div"
                );

            div.textContent =
                value == null
                    ? ""
                    : String(value);

            return div.innerHTML;
        },

        parseBoolean(value) {
            return [
                "1",
                "true",
                "yes",
                "on",
            ].includes(
                String(value)
                    .toLowerCase()
            );
        },

        getCookie(name) {
            const cookieValue =
                document.cookie
                    .split(";")
                    .map(
                        (item) =>
                            item.trim()
                    )
                    .find(
                        (item) =>
                            item.startsWith(
                                `${name}=`
                            )
                    );

            if (!cookieValue) {
                return null;
            }

            return decodeURIComponent(
                cookieValue
                    .split("=")
                    .slice(1)
                    .join("=")
            );
        },

        dispatch(
            name,
            detail = {}
        ) {
            document.dispatchEvent(
                new CustomEvent(
                    name,
                    {
                        detail,
                    }
                )
            );
        },

        dispatchReady() {
            this.dispatch(
                "abwaab:ready",
                {
                    app: this,
                }
            );
        },

        /* =====================================================
           شاشة التحميل العامة
        ===================================================== */

        showLoading(
            options = {}
        ) {
            const overlay =
                this.elements
                    .loadingOverlay;

            if (!overlay) {
                return;
            }

            const {
                title =
                    "جارٍ تنفيذ العملية",

                message =
                    "يرجى الانتظار قليلًا...",

                delay =
                    this.config
                        .loadingDelay,
            } = options;

            window.clearTimeout(
                this.state
                    .loadingTimer
            );

            if (
                this.elements
                    .loadingTitle
            ) {
                this.elements
                    .loadingTitle
                    .textContent =
                    title;
            }

            if (
                this.elements
                    .loadingMessage
            ) {
                this.elements
                    .loadingMessage
                    .textContent =
                    message;
            }

            this.state.loadingTimer =
                window.setTimeout(
                    () => {
                        overlay.hidden =
                            false;

                        overlay.setAttribute(
                            "aria-hidden",
                            "false"
                        );

                        document.body
                            .classList
                            .add(
                                "app-is-loading"
                            );
                    },
                    Math.max(
                        0,
                        Number(delay) ||
                        0
                    )
                );
        },

        hideLoading() {
            const overlay =
                this.elements
                    .loadingOverlay;

            window.clearTimeout(
                this.state
                    .loadingTimer
            );

            if (!overlay) {
                return;
            }

            overlay.hidden =
                true;

            overlay.setAttribute(
                "aria-hidden",
                "true"
            );

            document.body
                .classList
                .remove(
                    "app-is-loading"
                );
        },

        /* =====================================================
           Toast
        ===================================================== */

        toast(
            message,
            options = {}
        ) {
            const container =
                this.elements
                    .toastContainer;

            if (
                !container ||
                !message
            ) {
                return null;
            }

            const {
                type = "info",

                title =
                    this.getToastTitle(
                        type
                    ),

                timeout =
                    this.config
                        .toastTimeout,

                closable = true,
            } = options;

            const toast =
                document.createElement(
                    "article"
                );

            toast.className = [
                "app-toast",
                `app-toast-${type}`,
            ].join(" ");

            toast.setAttribute(
                "role",
                "status"
            );

            const icon =
                this.getToastIcon(
                    type
                );

            toast.innerHTML = `
                <span
                    class="app-toast-icon"
                    aria-hidden="true"
                >
                    ${icon}
                </span>

                <div class="app-toast-content">

                    <strong class="app-toast-title">
                        ${this.escapeHtml(title)}
                    </strong>

                    <p class="app-toast-message">
                        ${this.escapeHtml(message)}
                    </p>

                </div>

                ${
                    closable
                        ? `
                            <button
                                type="button"
                                class="app-toast-close"
                                aria-label="إغلاق الإشعار"
                            >
                                ×
                            </button>
                        `
                        : ""
                }
            `;

            container.appendChild(
                toast
            );

            const closeButton =
                toast.querySelector(
                    ".app-toast-close"
                );

            const removeToast =
                () => {
                    if (
                        !toast.isConnected
                    ) {
                        return;
                    }

                    toast.classList.add(
                        "is-leaving"
                    );

                    window.setTimeout(
                        () => {
                            toast.remove();
                        },
                        220
                    );
                };

            if (closeButton) {
                closeButton
                    .addEventListener(
                        "click",
                        removeToast
                    );
            }

            if (timeout !== 0) {
                window.setTimeout(
                    removeToast,
                    Number(timeout) ||
                    0
                );
            }

            return toast;
        },

        getToastTitle(type) {
            const titles = {
                success:
                    "تمت العملية بنجاح",

                warning:
                    "تنبيه",

                danger:
                    "تعذر تنفيذ العملية",

                error:
                    "تعذر تنفيذ العملية",

                info:
                    "إشعار",
            };

            return (
                titles[type] ||
                titles.info
            );
        },

        getToastIcon(type) {
            const icons = {
                success: "✓",
                warning: "!",
                danger: "!",
                error: "!",
                info: "i",
            };

            return (
                icons[type] ||
                icons.info
            );
        },

        /* =====================================================
           رسائل Django
        ===================================================== */

        initAlerts(
            root = document
        ) {
            this.qsa(
                "[data-dismiss-alert]",
                root
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .alertCloseInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .alertCloseInitialized =
                        "true";

                    button.addEventListener(
                        "click",
                        () => {
                            const alert =
                                button.closest(
                                    ".app-alert, .alert"
                                );

                            this.dismissAlert(
                                alert
                            );
                        }
                    );
                }
            );

            this.qsa(
                `
                    .app-alert[data-auto-dismiss="true"],
                    .alert[data-auto-dismiss="true"]
                `,
                root
            ).forEach(
                (alert) => {
                    if (
                        alert.dataset
                            .autoDismissInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    alert.dataset
                        .autoDismissInitialized =
                        "true";

                    const timeout =
                        Number(
                            alert.dataset
                                .dismissAfter
                        ) ||
                        this.config
                            .alertTimeout;

                    window.setTimeout(
                        () => {
                            this.dismissAlert(
                                alert
                            );
                        },
                        timeout
                    );
                }
            );
        },

        dismissAlert(alert) {
            if (!alert) {
                return;
            }

            alert.style.transition =
                "opacity 180ms ease, transform 180ms ease";

            alert.style.opacity =
                "0";

            alert.style.transform =
                "translateY(-8px)";

            window.setTimeout(
                () => {
                    alert.remove();
                },
                190
            );
        },

        /* =====================================================
           نظام المظهر الموحد
        ===================================================== */

        initTheme() {
            const legacyTheme =
                window.localStorage
                    .getItem(
                        this.config
                            .legacyThemeStorageKey
                    );

            const savedTheme =
                window.localStorage
                    .getItem(
                        this.config
                            .themeStorageKey
                    );

            /*
             * النظام الجديد له الأولوية.
             * عند عدم وجود قيمة محفوظة يكون الوضع الفاتح هو الافتراضي.
             */
            const initialTheme =
                this.normalizeTheme(
                    savedTheme ||
                    legacyTheme ||
                    this.config
                        .defaultTheme
                );

            /*
             * حذف المفتاح القديم نهائيًا لمنع أي سكربت قديم
             * من إعادة تشغيل الوضع الليلي.
             */
            window.localStorage
                .removeItem(
                    this.config
                        .legacyThemeStorageKey
                );

            this.applyTheme(
                initialTheme,
                false
            );

            this.qsa(
                `
                    [data-theme-toggle],
                    .theme-toggle,
                    #themeBtn
                `
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .themeInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .themeInitialized =
                        "true";

                    button.setAttribute(
                        "type",
                        "button"
                    );

                    button.addEventListener(
                        "click",
                        (event) => {
                            event.preventDefault();

                            const currentTheme =
                                this.getCurrentTheme();

                            const nextTheme =
                                currentTheme ===
                                "dark"
                                    ? "light"
                                    : "dark";

                            this.applyTheme(
                                nextTheme,
                                true
                            );
                        }
                    );
                }
            );
        },

        normalizeTheme(theme) {
            return (
                String(theme)
                    .toLowerCase() ===
                "dark"
                    ? "dark"
                    : "light"
            );
        },

        getCurrentTheme() {
            return (
                document.body
                    .classList
                    .contains("dark")
                    ? "dark"
                    : "light"
            );
        },

        applyTheme(
            theme,
            persist = true
        ) {
            const normalizedTheme =
                this.normalizeTheme(
                    theme
                );

            const isDark =
                normalizedTheme ===
                "dark";

            /*
             * توحيد حالة body وhtml معًا.
             */
            document.body
                .classList
                .toggle(
                    "dark",
                    isDark
                );

            document.documentElement
                .classList
                .toggle(
                    "dark",
                    isDark
                );

            document.documentElement
                .dataset
                .theme =
                normalizedTheme;

            document.documentElement
                .style
                .colorScheme =
                normalizedTheme;

            /*
             * تحديث جميع أزرار المظهر.
             */
            this.qsa(
                `
                    [data-theme-toggle],
                    .theme-toggle,
                    #themeBtn
                `
            ).forEach(
                (button) => {
                    button.setAttribute(
                        "aria-pressed",
                        String(isDark)
                    );

                    button.setAttribute(
                        "aria-label",
                        isDark
                            ? "تفعيل الوضع الفاتح"
                            : "تفعيل الوضع الداكن"
                    );

                    button.setAttribute(
                        "title",
                        isDark
                            ? "تفعيل الوضع الفاتح"
                            : "تفعيل الوضع الداكن"
                    );

                    const icon =
                        button.querySelector(
                            `
                                [data-theme-icon],
                                .theme-toggle-icon
                            `
                        );

                    if (icon) {
                        icon.textContent =
                            isDark
                                ? "☀️"
                                : "🌙";
                    } else if (
                        button.id ===
                        "themeBtn"
                    ) {
                        button.textContent =
                            isDark
                                ? "☀️"
                                : "🌙";
                    }
                }
            );

            if (persist) {
                window.localStorage
                    .setItem(
                        this.config
                            .themeStorageKey,
                        normalizedTheme
                    );
            }

            /*
             * إزالة المفتاح القديم بعد كل تغيير.
             */
            window.localStorage
                .removeItem(
                    this.config
                        .legacyThemeStorageKey
                );

            this.dispatch(
                "abwaab:theme-changed",
                {
                    theme:
                        normalizedTheme,

                    isDark,
                }
            );
        },

        resetTheme() {
            window.localStorage
                .removeItem(
                    this.config
                        .legacyThemeStorageKey
                );

            window.localStorage
                .setItem(
                    this.config
                        .themeStorageKey,
                    "light"
                );

            this.applyTheme(
                "light",
                false
            );
        },

        /* =====================================================
           القوائم المنسدلة
        ===================================================== */

        initDropdowns(
            root = document
        ) {
            const dropdowns =
                this.qsa(
                    `
                        .app-dropdown,
                        [data-dropdown]
                    `,
                    root
                );

            dropdowns.forEach(
                (dropdown) => {
                    if (
                        dropdown.dataset
                            .dropdownInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    const toggle =
                        dropdown.querySelector(
                            `
                                [data-dropdown-toggle],
                                .app-dropdown-toggle
                            `
                        );

                    const menu =
                        dropdown.querySelector(
                            `
                                [data-dropdown-menu],
                                .app-dropdown-menu
                            `
                        );

                    if (
                        !toggle ||
                        !menu
                    ) {
                        return;
                    }

                    dropdown.dataset
                        .dropdownInitialized =
                        "true";

                    toggle.setAttribute(
                        "aria-haspopup",
                        "true"
                    );

                    toggle.setAttribute(
                        "aria-expanded",
                        "false"
                    );

                    toggle.addEventListener(
                        "click",
                        (event) => {
                            event.preventDefault();
                            event.stopPropagation();

                            const willOpen =
                                !dropdown
                                    .classList
                                    .contains(
                                        "open"
                                    );

                            this.closeDropdowns(
                                dropdown
                            );

                            dropdown
                                .classList
                                .toggle(
                                    "open",
                                    willOpen
                                );

                            menu.classList
                                .toggle(
                                    "show",
                                    willOpen
                                );

                            toggle.setAttribute(
                                "aria-expanded",
                                String(
                                    willOpen
                                )
                            );

                            this.state
                                .activeDropdown =
                                willOpen
                                    ? dropdown
                                    : null;
                        }
                    );

                    dropdown.addEventListener(
                        "keydown",
                        (event) => {
                            if (
                                event.key ===
                                "Escape"
                            ) {
                                this.closeDropdown(
                                    dropdown
                                );

                                toggle.focus();
                            }
                        }
                    );
                }
            );

            if (
                document.documentElement
                    .dataset
                    .dropdownGlobalInitialized !==
                "true"
            ) {
                document.documentElement
                    .dataset
                    .dropdownGlobalInitialized =
                    "true";

                document.addEventListener(
                    "click",
                    (event) => {
                        const active =
                            this.state
                                .activeDropdown;

                        if (
                            active &&
                            !active.contains(
                                event.target
                            )
                        ) {
                            this.closeDropdown(
                                active
                            );
                        }
                    }
                );

                document.addEventListener(
                    "keydown",
                    (event) => {
                        if (
                            event.key ===
                                "Escape" &&
                            this.state
                                .activeDropdown
                        ) {
                            this.closeDropdown(
                                this.state
                                    .activeDropdown
                            );
                        }
                    }
                );
            }
        },

        closeDropdown(dropdown) {
            if (!dropdown) {
                return;
            }

            dropdown.classList
                .remove(
                    "open"
                );

            const toggle =
                dropdown.querySelector(
                    `
                        [data-dropdown-toggle],
                        .app-dropdown-toggle
                    `
                );

            const menu =
                dropdown.querySelector(
                    `
                        [data-dropdown-menu],
                        .app-dropdown-menu
                    `
                );

            if (menu) {
                menu.classList
                    .remove(
                        "show"
                    );
            }

            if (toggle) {
                toggle.setAttribute(
                    "aria-expanded",
                    "false"
                );
            }

            if (
                this.state
                    .activeDropdown ===
                dropdown
            ) {
                this.state
                    .activeDropdown =
                    null;
            }
        },

        closeDropdowns(
            except = null
        ) {
            this.qsa(
                `
                    .app-dropdown.open,
                    [data-dropdown].open
                `
            ).forEach(
                (dropdown) => {
                    if (
                        dropdown !==
                        except
                    ) {
                        this.closeDropdown(
                            dropdown
                        );
                    }
                }
            );
        },

        /* =====================================================
           Accordion
        ===================================================== */

        initAccordions(
            root = document
        ) {
            this.qsa(
                `
                    [data-accordion-trigger],
                    .app-accordion-trigger
                `,
                root
            ).forEach(
                (trigger) => {
                    if (
                        trigger.dataset
                            .accordionInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    const targetSelector =
                        trigger.dataset
                            .accordionTarget;

                    let content =
                        null;

                    if (targetSelector) {
                        content =
                            document.querySelector(
                                targetSelector
                            );
                    } else {
                        content =
                            trigger
                                .nextElementSibling;
                    }

                    if (!content) {
                        return;
                    }

                    trigger.dataset
                        .accordionInitialized =
                        "true";

                    const item =
                        trigger.closest(
                            ".app-accordion-item"
                        );

                    const initiallyOpen =
                        trigger.getAttribute(
                            "aria-expanded"
                        ) === "true" ||
                        item?.classList
                            .contains(
                                "open"
                            );

                    content.hidden =
                        !initiallyOpen;

                    trigger.setAttribute(
                        "aria-expanded",
                        String(
                            initiallyOpen
                        )
                    );

                    trigger.addEventListener(
                        "click",
                        () => {
                            const isOpen =
                                trigger.getAttribute(
                                    "aria-expanded"
                                ) ===
                                "true";

                            trigger.setAttribute(
                                "aria-expanded",
                                String(
                                    !isOpen
                                )
                            );

                            content.hidden =
                                isOpen;

                            item?.classList
                                .toggle(
                                    "open",
                                    !isOpen
                                );
                        }
                    );
                }
            );
        },

        /* =====================================================
           Drawer
        ===================================================== */

        initDrawers(
            root = document
        ) {
            this.qsa(
                "[data-drawer-open]",
                root
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .drawerOpenInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .drawerOpenInitialized =
                        "true";

                    button.addEventListener(
                        "click",
                        () => {
                            const selector =
                                button.dataset
                                    .drawerOpen;

                            const drawer =
                                document
                                    .querySelector(
                                        selector
                                    );

                            this.openDrawer(
                                drawer
                            );
                        }
                    );
                }
            );

            this.qsa(
                `
                    [data-drawer-close],
                    .app-drawer-backdrop
                `,
                root
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .drawerCloseInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .drawerCloseInitialized =
                        "true";

                    button.addEventListener(
                        "click",
                        () => {
                            const drawer =
                                button.closest(
                                    ".app-drawer"
                                );

                            this.closeDrawer(
                                drawer
                            );
                        }
                    );
                }
            );
        },

        openDrawer(drawer) {
            if (!drawer) {
                return;
            }

            drawer.classList.add(
                "open"
            );

            drawer.setAttribute(
                "aria-hidden",
                "false"
            );

            document.body
                .classList
                .add(
                    "app-overlay-open"
                );
        },

        closeDrawer(drawer) {
            if (!drawer) {
                return;
            }

            drawer.classList.remove(
                "open"
            );

            drawer.setAttribute(
                "aria-hidden",
                "true"
            );

            document.body
                .classList
                .remove(
                    "app-overlay-open"
                );
        },

        /* =====================================================
           حقول الملفات
        ===================================================== */

        initFileInputs(
            root = document
        ) {
            this.qsa(
                'input[type="file"]',
                root
            ).forEach(
                (input) => {
                    if (
                        input.dataset
                            .fileInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    input.dataset
                        .fileInitialized =
                        "true";

                    input.addEventListener(
                        "change",
                        () => {
                            const file =
                                input.files?.[0] ||
                                null;

                            const wrapper =
                                input.closest(
                                    `
                                        .app-file-upload,
                                        .attachment-upload-field,
                                        .maintenance-upload-box
                                    `
                                );

                            if (!wrapper) {
                                return;
                            }

                            const filenameTarget =
                                wrapper.querySelector(
                                    "[data-file-name]"
                                );

                            if (
                                filenameTarget
                            ) {
                                filenameTarget
                                    .textContent =
                                    file?.name ||
                                    "لم يتم اختيار ملف";
                            }

                            const previewTargetSelector =
                                input.dataset
                                    .previewTarget;

                            if (
                                file &&
                                previewTargetSelector &&
                                file.type
                                    .startsWith(
                                        "image/"
                                    )
                            ) {
                                this.previewImage(
                                    file,
                                    document
                                        .querySelector(
                                            previewTargetSelector
                                        )
                                );
                            }
                        }
                    );
                }
            );
        },

        previewImage(
            file,
            target
        ) {
            if (
                !file ||
                !target
            ) {
                return;
            }

            const reader =
                new FileReader();

            reader.onload =
                (event) => {
                    let image =
                        target
                            .querySelector(
                                "img"
                            );

                    if (!image) {
                        image =
                            document
                                .createElement(
                                    "img"
                                );

                        target.innerHTML =
                            "";

                        target.appendChild(
                            image
                        );
                    }

                    image.src =
                        event.target
                            .result;

                    image.alt =
                        file.name;

                    target.hidden =
                        false;
                };

            reader.readAsDataURL(
                file
            );
        },

        /* =====================================================
           إظهار وإخفاء كلمة المرور
        ===================================================== */

        initPasswordToggles(
            root = document
        ) {
            this.qsa(
                "[data-password-toggle]",
                root
            ).forEach(
                (button) => {
                    if (
                        button.dataset
                            .passwordInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset
                        .passwordInitialized =
                        "true";

                    button.addEventListener(
                        "click",
                        () => {
                            const selector =
                                button.dataset
                                    .passwordToggle;

                            const input =
                                document
                                    .querySelector(
                                        selector
                                    );

                            if (!input) {
                                return;
                            }

                            const showPassword =
                                input.type ===
                                "password";

                            input.type =
                                showPassword
                                    ? "text"
                                    : "password";

                            button.setAttribute(
                                "aria-pressed",
                                String(
                                    showPassword
                                )
                            );

                            button.setAttribute(
                                "aria-label",
                                showPassword
                                    ? "إخفاء كلمة المرور"
                                    : "إظهار كلمة المرور"
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           الإرسال التلقائي
        ===================================================== */

        initAutoSubmit(
            root = document
        ) {
            this.qsa(
                "[data-auto-submit]",
                root
            ).forEach(
                (field) => {
                    if (
                        field.dataset
                            .autoSubmitInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    field.dataset
                        .autoSubmitInitialized =
                        "true";

                    const delay =
                        Number(
                            field.dataset
                                .autoSubmitDelay
                        ) ||
                        350;

                    const handler =
                        this.debounce(
                            () => {
                                const form =
                                    field.closest(
                                        "form"
                                    );

                                if (!form) {
                                    return;
                                }

                                if (
                                    typeof form
                                        .requestSubmit ===
                                    "function"
                                ) {
                                    form.requestSubmit();
                                } else {
                                    form.submit();
                                }
                            },
                            delay
                        );

                    const eventName =
                        field.matches(
                            `
                                select,
                                input[type="checkbox"],
                                input[type="radio"]
                            `
                        )
                            ? "change"
                            : "input";

                    field.addEventListener(
                        eventName,
                        handler
                    );
                }
            );
        },

        /* =====================================================
           النماذج العامة
        ===================================================== */

        initForms(
            root = document
        ) {
            this.qsa(
                'form[data-show-loading="true"]',
                root
            ).forEach(
                (form) => {
                    if (
                        form.dataset
                            .showLoadingInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    form.dataset
                        .showLoadingInitialized =
                        "true";

                    form.addEventListener(
                        "submit",
                        () => {
                            if (
                                !form
                                    .checkValidity()
                            ) {
                                return;
                            }

                            this.showLoading({
                                title:
                                    form.dataset
                                        .loadingTitle ||
                                    "جارٍ حفظ البيانات",

                                message:
                                    form.dataset
                                        .loadingMessage ||
                                    "يتم الآن تنفيذ طلبك...",
                            });
                        }
                    );
                }
            );

            this.qsa(
                'form[data-prevent-double-submit="true"]',
                root
            ).forEach(
                (form) => {
                    if (
                        form.dataset
                            .doubleSubmitInitialized ===
                        "true"
                    ) {
                        return;
                    }

                    form.dataset
                        .doubleSubmitInitialized =
                        "true";

                    form.addEventListener(
                        "submit",
                        () => {
                            if (
                                !form
                                    .checkValidity()
                            ) {
                                return;
                            }

                            const submitButtons =
                                form.querySelectorAll(
                                    `
                                        button[type="submit"],
                                        input[type="submit"]
                                    `
                                );

                            submitButtons.forEach(
                                (button) => {
                                    button.disabled =
                                        true;

                                    button
                                        .classList
                                        .add(
                                            "is-loading"
                                        );
                                }
                            );
                        }
                    );
                }
            );
        },

        /* =====================================================
           الروابط الخارجية
        ===================================================== */

        initExternalLinks(
            root = document
        ) {
            this.qsa(
                'a[target="_blank"]',
                root
            ).forEach(
                (link) => {
                    const rel =
                        new Set(
                            (
                                link.getAttribute(
                                    "rel"
                                ) ||
                                ""
                            )
                                .split(/\s+/)
                                .filter(
                                    Boolean
                                )
                        );

                    rel.add(
                        "noopener"
                    );

                    rel.add(
                        "noreferrer"
                    );

                    link.setAttribute(
                        "rel",
                        Array.from(
                            rel
                        ).join(" ")
                    );
                }
            );
        },

        /* =====================================================
           اختصارات لوحة المفاتيح
        ===================================================== */

        initGlobalShortcuts() {
            if (
                document.documentElement
                    .dataset
                    .shortcutsInitialized ===
                "true"
            ) {
                return;
            }

            document.documentElement
                .dataset
                .shortcutsInitialized =
                "true";

            document.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key ===
                            "/" &&
                        !event.ctrlKey &&
                        !event.metaKey &&
                        !event.altKey
                    ) {
                        const activeElement =
                            document
                                .activeElement;

                        const isTyping =
                            activeElement &&
                            (
                                activeElement
                                    .tagName ===
                                    "INPUT" ||

                                activeElement
                                    .tagName ===
                                    "TEXTAREA" ||

                                activeElement
                                    .isContentEditable
                            );

                        if (isTyping) {
                            return;
                        }

                        const searchInput =
                            document
                                .querySelector(
                                    `
                                        [data-global-search],
                                        .app-search input,
                                        .datagrid-search input
                                    `
                                );

                        if (searchInput) {
                            event.preventDefault();

                            searchInput.focus();
                        }
                    }

                    if (
                        event.key ===
                        "Escape"
                    ) {
                        this.qsa(
                            ".app-drawer.open"
                        ).forEach(
                            (drawer) => {
                                this.closeDrawer(
                                    drawer
                                );
                            }
                        );
                    }
                }
            );
        },
    };

    /* =========================================================
       إتاحة التطبيق عالميًا
    ========================================================= */

    window.AbwaabApp =
        App;

    window.showAppLoading =
        function (options) {
            return App.showLoading(
                options
            );
        };

    window.hideAppLoading =
        function () {
            return App.hideLoading();
        };

    window.showToast =
        function (
            message,
            options
        ) {
            return App.toast(
                message,
                options
            );
        };

    window.setAbwaabTheme =
        function (theme) {
            return App.applyTheme(
                theme,
                true
            );
        };

    window.resetAbwaabTheme =
        function () {
            return App.resetTheme();
        };

    /* =========================================================
       تشغيل التطبيق
    ========================================================= */

    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                App.init();
            },
            {
                once: true,
            }
        );
    } else {
        App.init();
    }

    /* =========================================================
       معالجة الرجوع من ذاكرة المتصفح
    ========================================================= */

    window.addEventListener(
        "pageshow",
        () => {
            App.hideLoading();

            const savedTheme =
                window.localStorage
                    .getItem(
                        App.config
                            .themeStorageKey
                    ) ||
                App.config
                    .defaultTheme;

            App.applyTheme(
                savedTheme,
                false
            );
        }
    );

    /* =========================================================
       تسجيل أخطاء الوعود غير المعالجة
    ========================================================= */

    window.addEventListener(
        "unhandledrejection",
        (event) => {
            console.error(
                "Unhandled Promise Rejection:",
                event.reason
            );
        }
    );
})();