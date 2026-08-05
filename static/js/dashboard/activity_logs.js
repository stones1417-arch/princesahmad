(() => {
    "use strict";

    const byId = (id) => document.getElementById(id);
    const modal = byId("activityDetailsModal");

    function safeText(value, fallback = "—") {
        const text = String(value ?? "").trim();
        return text || fallback;
    }

    function setText(id, value, fallback = "—") {
        const element = byId(id);

        if (element) {
            element.textContent = safeText(value, fallback);
        }
    }

    function showToast(message, type = "success") {
        const container = byId("activityToastContainer");

        if (!container) {
            return;
        }

        const toast = document.createElement("div");
        toast.className = `activity-toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        window.setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(-24px)";

            window.setTimeout(() => {
                toast.remove();
            }, 250);
        }, 2500);
    }

    window.openActivityDetails = function (
        user,
        module,
        action,
        description,
        ipAddress,
        createdAt,
        actionCode
    ) {
        if (!modal) {
            return;
        }

        const userName = safeText(user, "مستخدم النظام");

        setText(
            "modalActivityAvatar",
            userName.charAt(0) || "م",
            "م"
        );
        setText("modalActivityUser", userName);
        setText("modalActivityModule", module);
        setText("modalActivityAction", action);
        setText("modalActivityDescription", description);
        setText("modalActivityIp", ipAddress);
        setText("modalActivityDate", createdAt);

        const actionBadge = byId("modalActivityAction");

        if (actionBadge) {
            actionBadge.className =
                `activity-modal-action action-${safeText(actionCode, "other")}`;
        }

        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
    };

    window.closeActivityDetails = function () {
        if (!modal) {
            return;
        }

        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
    };

    window.copyActivityIp = async function () {
        const ipAddress = safeText(
            byId("modalActivityIp")?.textContent,
            ""
        );

        if (!ipAddress || ipAddress === "—") {
            showToast("لا يوجد عنوان IP لنسخه.", "error");
            return;
        }

        try {
            await navigator.clipboard.writeText(ipAddress);
            showToast("تم نسخ عنوان IP.");
        } catch {
            showToast("تعذر نسخ عنوان IP.", "error");
        }
    };

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            window.closeActivityDetails();
        }
    });
})();
