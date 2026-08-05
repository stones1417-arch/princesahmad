/* =========================================================
   منصة أبواب — إدارة النوافذ المنبثقة
   الملف: static/js/modals.js
   الإصدار: 2026.07.28
========================================================= */

(function () {
    "use strict";

    const ModalManager = {
        config: {
            animationDuration: 220,
            modalSelector: ".app-modal, .modal-backdrop",
            openClass: "is-open",
            legacyOpenClass: "active",
        },

        state: {
            activeModal: null,
            lastFocusedElement: null,
            confirmCallback: null,
            cancelCallback: null,
        },

        init() {
            this.cacheElements();
            this.initOpenButtons();
            this.initCloseButtons();
            this.initBackdropClosing();
            this.initKeyboardControls();
            this.initConfirmDialog();
            this.normalizeInitialState();
            this.dispatchReady();
        },

        cacheElements() {
            this.elements = {
                body: document.body,

                confirmDialog:
                    document.getElementById(
                        "appConfirmDialog"
                    ),

                confirmTitle:
                    document.getElementById(
                        "appConfirmTitle"
                    ),

                confirmMessage:
                    document.getElementById(
                        "appConfirmMessage"
                    ),

                confirmButton:
                    document.getElementById(
                        "appConfirmButton"
                    ),
            };
        },

        /* =====================================================
           أدوات عامة
        ===================================================== */

        qsa(selector, root = document) {
            return Array.from(
                root.querySelectorAll(selector)
            );
        },

        dispatch(name, detail = {}) {
            document.dispatchEvent(
                new CustomEvent(name, {
                    detail,
                })
            );
        },

        dispatchReady() {
            this.dispatch(
                "abwaab:modals-ready",
                {
                    manager: this,
                }
            );
        },

        resolveModal(target) {
            if (!target) {
                return null;
            }

            if (target instanceof HTMLElement) {
                return target;
            }

            if (typeof target !== "string") {
                return null;
            }

            try {
                return document.querySelector(
                    target
                );
            } catch (error) {
                console.error(
                    "Invalid modal selector:",
                    target,
                    error
                );

                return null;
            }
        },

        isModalOpen(modal) {
            if (!modal) {
                return false;
            }

            return (
                modal.classList.contains(
                    this.config.openClass
                ) ||
                modal.classList.contains(
                    this.config.legacyOpenClass
                ) ||
                modal.getAttribute(
                    "aria-hidden"
                ) === "false"
            );
        },

        /* =====================================================
           تهيئة الحالة
        ===================================================== */

        normalizeInitialState() {
            this.qsa(
                this.config.modalSelector
            ).forEach((modal) => {
                const shouldRemainOpen =
                    modal.classList.contains(
                        this.config.openClass
                    ) ||
                    modal.classList.contains(
                        this.config.legacyOpenClass
                    );

                if (shouldRemainOpen) {
                    modal.hidden = false;

                    modal.setAttribute(
                        "aria-hidden",
                        "false"
                    );
                } else {
                    modal.hidden = true;

                    modal.setAttribute(
                        "aria-hidden",
                        "true"
                    );
                }
            });
        },

        /* =====================================================
           فتح النوافذ
        ===================================================== */

        initOpenButtons() {
            document.addEventListener(
                "click",
                (event) => {
                    const trigger =
                        event.target.closest(
                            `
                                [data-modal-open],
                                [data-open-modal],
                                [data-bs-target]
                            `
                        );

                    if (!trigger) {
                        return;
                    }

                    const target =
                        trigger.dataset.modalOpen ||
                        trigger.dataset.openModal ||
                        trigger.dataset.bsTarget;

                    if (!target) {
                        return;
                    }

                    const modal =
                        this.resolveModal(target);

                    if (!modal) {
                        return;
                    }

                    event.preventDefault();

                    this.open(
                        modal,
                        {
                            trigger,
                        }
                    );
                }
            );
        },

        open(target, options = {}) {
            const modal =
                this.resolveModal(target);

            if (!modal) {
                return false;
            }

            const {
                trigger = document.activeElement,
                closeOthers = true,
                focus = true,
            } = options;

            if (
                closeOthers &&
                this.state.activeModal &&
                this.state.activeModal !== modal
            ) {
                this.close(
                    this.state.activeModal,
                    {
                        restoreFocus: false,
                    }
                );
            }

            this.state.lastFocusedElement =
                trigger instanceof HTMLElement
                    ? trigger
                    : document.activeElement;

            modal.hidden = false;

            modal.setAttribute(
                "aria-hidden",
                "false"
            );

            modal.classList.add(
                this.config.openClass
            );

            modal.classList.add(
                this.config.legacyOpenClass
            );

            this.elements.body.classList.add(
                "app-modal-open"
            );

            this.elements.body.classList.add(
                "app-overlay-open"
            );

            this.state.activeModal =
                modal;

            if (focus) {
                window.requestAnimationFrame(
                    () => {
                        this.focusFirstElement(
                            modal
                        );
                    }
                );
            }

            this.dispatch(
                "abwaab:modal-opened",
                {
                    modal,
                    trigger,
                }
            );

            return true;
        },

        /* =====================================================
           إغلاق النوافذ
        ===================================================== */

        initCloseButtons() {
            document.addEventListener(
                "click",
                (event) => {
                    const closeButton =
                        event.target.closest(
                            `
                                [data-modal-close],
                                [data-close-modal],
                                .app-modal-close,
                                .modal-close
                            `
                        );

                    if (!closeButton) {
                        return;
                    }

                    const modal =
                        closeButton.closest(
                            this.config.modalSelector
                        );

                    if (!modal) {
                        return;
                    }

                    event.preventDefault();

                    this.close(modal);
                }
            );
        },

        close(target, options = {}) {
            const modal =
                this.resolveModal(target);

            if (!modal) {
                return false;
            }

            const {
                restoreFocus = true,
                immediate = false,
            } = options;

            modal.classList.remove(
                this.config.openClass
            );

            modal.classList.remove(
                this.config.legacyOpenClass
            );

            modal.setAttribute(
                "aria-hidden",
                "true"
            );

            const finishClose = () => {
                modal.hidden = true;

                if (
                    this.state.activeModal ===
                    modal
                ) {
                    this.state.activeModal =
                        null;
                }

                const hasOpenModal =
                    this.qsa(
                        this.config.modalSelector
                    ).some((item) => {
                        return this.isModalOpen(
                            item
                        );
                    });

                if (!hasOpenModal) {
                    this.elements.body.classList.remove(
                        "app-modal-open"
                    );

                    this.elements.body.classList.remove(
                        "app-overlay-open"
                    );
                }

                if (
                    restoreFocus &&
                    this.state.lastFocusedElement &&
                    typeof this.state.lastFocusedElement.focus ===
                        "function"
                ) {
                    this.state.lastFocusedElement.focus();
                }

                this.dispatch(
                    "abwaab:modal-closed",
                    {
                        modal,
                    }
                );
            };

            if (immediate) {
                finishClose();
            } else {
                window.setTimeout(
                    finishClose,
                    this.config.animationDuration
                );
            }

            return true;
        },

        closeAll(options = {}) {
            this.qsa(
                this.config.modalSelector
            ).forEach((modal) => {
                if (this.isModalOpen(modal)) {
                    this.close(
                        modal,
                        {
                            ...options,
                            restoreFocus: false,
                        }
                    );
                }
            });

            if (
                options.restoreFocus !==
                    false &&
                this.state.lastFocusedElement &&
                typeof this.state.lastFocusedElement.focus ===
                    "function"
            ) {
                window.setTimeout(() => {
                    this.state.lastFocusedElement.focus();
                }, this.config.animationDuration);
            }
        },

        /* =====================================================
           إغلاق بالضغط على الخلفية
        ===================================================== */

        initBackdropClosing() {
            document.addEventListener(
                "click",
                (event) => {
                    const backdrop =
                        event.target.closest(
                            `
                                [data-modal-close],
                                .app-modal-backdrop
                            `
                        );

                    if (!backdrop) {
                        return;
                    }

                    const modal =
                        backdrop.closest(
                            this.config.modalSelector
                        );

                    if (!modal) {
                        return;
                    }

                    if (
                        modal.dataset.backdrop ===
                        "static"
                    ) {
                        this.shake(modal);
                        return;
                    }

                    if (
                        event.target === backdrop
                    ) {
                        this.close(modal);
                    }
                }
            );
        },

        shake(modal) {
            const dialog =
                modal.querySelector(
                    `
                        .app-modal-dialog,
                        .modal
                    `
                );

            if (!dialog) {
                return;
            }

            dialog.classList.remove(
                "app-modal-shake"
            );

            void dialog.offsetWidth;

            dialog.classList.add(
                "app-modal-shake"
            );

            window.setTimeout(() => {
                dialog.classList.remove(
                    "app-modal-shake"
                );
            }, 360);
        },

        /* =====================================================
           التحكم بلوحة المفاتيح
        ===================================================== */

        initKeyboardControls() {
            document.addEventListener(
                "keydown",
                (event) => {
                    const modal =
                        this.state.activeModal;

                    if (!modal) {
                        return;
                    }

                    if (
                        event.key === "Escape"
                    ) {
                        if (
                            modal.dataset.keyboard ===
                            "false"
                        ) {
                            this.shake(modal);
                            return;
                        }

                        event.preventDefault();

                        this.close(modal);
                        return;
                    }

                    if (
                        event.key === "Tab"
                    ) {
                        this.trapFocus(
                            modal,
                            event
                        );
                    }
                }
            );
        },

        getFocusableElements(modal) {
            const selector = [
                "a[href]",
                "button:not([disabled])",
                "input:not([disabled])",
                "select:not([disabled])",
                "textarea:not([disabled])",
                '[tabindex]:not([tabindex="-1"])',
                '[contenteditable="true"]',
            ].join(",");

            return this.qsa(
                selector,
                modal
            ).filter((element) => {
                return (
                    !element.hidden &&
                    element.offsetParent !== null &&
                    element.getAttribute(
                        "aria-hidden"
                    ) !== "true"
                );
            });
        },

        focusFirstElement(modal) {
            const autofocus =
                modal.querySelector(
                    "[autofocus]"
                );

            if (
                autofocus &&
                !autofocus.disabled
            ) {
                autofocus.focus();
                return;
            }

            const focusable =
                this.getFocusableElements(
                    modal
                );

            if (focusable.length) {
                focusable[0].focus();
                return;
            }

            const dialog =
                modal.querySelector(
                    `
                        .app-modal-dialog,
                        .modal
                    `
                );

            if (dialog) {
                dialog.setAttribute(
                    "tabindex",
                    "-1"
                );

                dialog.focus();
            }
        },

        trapFocus(modal, event) {
            const focusable =
                this.getFocusableElements(
                    modal
                );

            if (!focusable.length) {
                event.preventDefault();
                return;
            }

            const firstElement =
                focusable[0];

            const lastElement =
                focusable[
                    focusable.length - 1
                ];

            if (
                event.shiftKey &&
                document.activeElement ===
                    firstElement
            ) {
                event.preventDefault();

                lastElement.focus();
            } else if (
                !event.shiftKey &&
                document.activeElement ===
                    lastElement
            ) {
                event.preventDefault();

                firstElement.focus();
            }
        },

        /* =====================================================
           نافذة التأكيد العامة
        ===================================================== */

        initConfirmDialog() {
            const dialog =
                this.elements.confirmDialog;

            const confirmButton =
                this.elements.confirmButton;

            if (!dialog || !confirmButton) {
                return;
            }

            confirmButton.addEventListener(
                "click",
                async () => {
                    const callback =
                        this.state.confirmCallback;

                    try {
                        confirmButton.disabled =
                            true;

                        confirmButton.classList.add(
                            "is-loading"
                        );

                        if (
                            typeof callback ===
                            "function"
                        ) {
                            const result =
                                await callback();

                            if (result === false) {
                                return;
                            }
                        }

                        this.close(dialog);
                    } catch (error) {
                        console.error(
                            "Confirm callback error:",
                            error
                        );

                        if (
                            window.showToast
                        ) {
                            window.showToast(
                                "حدث خطأ أثناء تنفيذ العملية.",
                                {
                                    type: "danger",
                                }
                            );
                        }
                    } finally {
                        confirmButton.disabled =
                            false;

                        confirmButton.classList.remove(
                            "is-loading"
                        );

                        this.state.confirmCallback =
                            null;
                    }
                }
            );

            dialog.addEventListener(
                "abwaab:modal-closed",
                () => {
                    this.resetConfirmDialog();
                }
            );
        },

        confirm(options = {}) {
            const dialog =
                this.elements.confirmDialog;

            if (!dialog) {
                return Promise.resolve(
                    window.confirm(
                        options.message ||
                        "هل أنت متأكد من تنفيذ هذه العملية؟"
                    )
                );
            }

            const {
                title = "تأكيد العملية",
                message =
                    "هل أنت متأكد من تنفيذ هذه العملية؟",
                confirmText = "تأكيد",
                cancelText = "إلغاء",
                type = "danger",
                onConfirm = null,
                onCancel = null,
            } = options;

            if (
                this.elements.confirmTitle
            ) {
                this.elements.confirmTitle.textContent =
                    title;
            }

            if (
                this.elements.confirmMessage
            ) {
                this.elements.confirmMessage.textContent =
                    message;
            }

            if (
                this.elements.confirmButton
            ) {
                this.elements.confirmButton.textContent =
                    confirmText;

                this.elements.confirmButton.className =
                    `app-btn app-btn-${type}`;

                this.elements.confirmButton.id =
                    "appConfirmButton";
            }

            const cancelButton =
                dialog.querySelector(
                    `
                        [data-modal-close].app-btn,
                        .app-modal-footer [data-modal-close]
                    `
                );

            if (cancelButton) {
                cancelButton.textContent =
                    cancelText;
            }

            this.state.confirmCallback =
                onConfirm;

            this.state.cancelCallback =
                onCancel;

            this.open(dialog);

            return new Promise((resolve) => {
                const confirmHandler =
                    async () => {
                        try {
                            if (
                                typeof onConfirm ===
                                "function"
                            ) {
                                const result =
                                    await onConfirm();

                                if (result === false) {
                                    return;
                                }
                            }

                            resolve(true);
                        } catch (error) {
                            console.error(
                                error
                            );

                            resolve(false);
                        }
                    };

                const cancelHandler =
                    async () => {
                        if (
                            typeof onCancel ===
                            "function"
                        ) {
                            await onCancel();
                        }

                        resolve(false);
                    };

                this.state.confirmCallback =
                    confirmHandler;

                const closeButtons =
                    this.qsa(
                        "[data-modal-close]",
                        dialog
                    );

                closeButtons.forEach(
                    (button) => {
                        button.addEventListener(
                            "click",
                            cancelHandler,
                            {
                                once: true,
                            }
                        );
                    }
                );
            });
        },

        resetConfirmDialog() {
            this.state.confirmCallback =
                null;

            this.state.cancelCallback =
                null;

            if (
                this.elements.confirmTitle
            ) {
                this.elements.confirmTitle.textContent =
                    "تأكيد العملية";
            }

            if (
                this.elements.confirmMessage
            ) {
                this.elements.confirmMessage.textContent =
                    "هل أنت متأكد من تنفيذ هذه العملية؟";
            }

            if (
                this.elements.confirmButton
            ) {
                this.elements.confirmButton.textContent =
                    "تأكيد";

                this.elements.confirmButton.className =
                    "app-btn app-btn-danger";

                this.elements.confirmButton.disabled =
                    false;
            }
        },

        /* =====================================================
           تأكيد الروابط والنماذج
        ===================================================== */

        initConfirmationTriggers() {
            document.addEventListener(
                "click",
                async (event) => {
                    const trigger =
                        event.target.closest(
                            "[data-confirm]"
                        );

                    if (!trigger) {
                        return;
                    }

                    if (
                        trigger.dataset.confirmed ===
                        "true"
                    ) {
                        return;
                    }

                    event.preventDefault();

                    const message =
                        trigger.dataset.confirm ||
                        "هل أنت متأكد من تنفيذ هذه العملية؟";

                    const title =
                        trigger.dataset.confirmTitle ||
                        "تأكيد العملية";

                    const type =
                        trigger.dataset.confirmType ||
                        "danger";

                    const approved =
                        await this.confirm({
                            title,
                            message,
                            type,
                            confirmText:
                                trigger.dataset.confirmButton ||
                                "تأكيد",
                        });

                    if (!approved) {
                        return;
                    }

                    trigger.dataset.confirmed =
                        "true";

                    if (
                        trigger.tagName === "A"
                    ) {
                        window.location.href =
                            trigger.href;
                    } else if (
                        trigger.closest("form")
                    ) {
                        const form =
                            trigger.closest("form");

                        if (
                            typeof form.requestSubmit ===
                            "function"
                        ) {
                            form.requestSubmit(
                                trigger
                            );
                        } else {
                            form.submit();
                        }
                    } else {
                        trigger.click();
                    }
                }
            );

            document.addEventListener(
                "submit",
                async (event) => {
                    const form =
                        event.target;

                    if (
                        !(form instanceof HTMLFormElement)
                    ) {
                        return;
                    }

                    if (
                        !form.dataset.confirmSubmit
                    ) {
                        return;
                    }

                    if (
                        form.dataset.confirmed ===
                        "true"
                    ) {
                        return;
                    }

                    event.preventDefault();

                    const approved =
                        await this.confirm({
                            title:
                                form.dataset.confirmTitle ||
                                "تأكيد العملية",

                            message:
                                form.dataset.confirmSubmit,

                            confirmText:
                                form.dataset.confirmButton ||
                                "تأكيد",

                            type:
                                form.dataset.confirmType ||
                                "danger",
                        });

                    if (!approved) {
                        return;
                    }

                    form.dataset.confirmed =
                        "true";

                    form.submit();
                }
            );
        },
    };

    /* =========================================================
       إضافة تهيئة تأكيد الروابط
    ========================================================= */

    const originalInit =
        ModalManager.init.bind(
            ModalManager
        );

    ModalManager.init = function () {
        originalInit();

        this.initConfirmationTriggers();
    };

    /* =========================================================
       إتاحة الدوال عالميًا
    ========================================================= */

    window.AbwaabModal =
        ModalManager;

    window.openAppModal = function (
        target,
        options
    ) {
        return ModalManager.open(
            target,
            options
        );
    };

    window.closeAppModal = function (
        target,
        options
    ) {
        return ModalManager.close(
            target,
            options
        );
    };

    window.closeAllAppModals =
        function (options) {
            return ModalManager.closeAll(
                options
            );
        };

    window.confirmAppAction =
        function (options) {
            return ModalManager.confirm(
                options
            );
        };

    /* =========================================================
       التشغيل
    ========================================================= */

    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                ModalManager.init();
            }
        );
    } else {
        ModalManager.init();
    }
})();