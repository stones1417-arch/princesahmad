(() => {
    "use strict";

    const modal = document.getElementById("employeeDetailsModal");

    const byId = (id) => document.getElementById(id);

    window.openEmployeeDetails = function (
        fullName, employeeNumber, phoneNumber, email, jobTitle,
        workStatus, systemStatus, doorsPermission,
        maintenancePermission, notes
    ) {
        if (!modal) return;

        const name = (fullName || "").trim() || "—";
        byId("modalEmployeeAvatar").textContent = name.charAt(0) || "م";
        byId("modalEmployeeName").textContent = name;
        byId("modalEmployeeNumber").textContent = employeeNumber || "—";
        byId("modalEmployeePhone").textContent = phoneNumber || "لا يوجد";
        byId("modalEmployeeEmail").textContent = email || "لا يوجد";
        byId("modalEmployeeJobTitle").textContent = jobTitle || "—";
        byId("modalEmployeeWorkStatus").textContent = workStatus || "—";
        byId("modalEmployeeDoorsPermission").textContent = doorsPermission || "لا";
        byId("modalEmployeeMaintenancePermission").textContent = maintenancePermission || "لا";
        byId("modalEmployeeNotes").textContent = (notes || "").trim() || "لا توجد ملاحظات";

        const status = byId("modalEmployeeSystemStatus");
        const active = systemStatus === "نشط";
        status.textContent = active ? "نشط" : "معطل";
        status.className = `employee-modal-status ${active ? "active" : "inactive"}`;

        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
    };

    window.closeEmployeeDetails = function () {
        if (!modal) return;
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
    };

    function getCsrfToken() {
        const cookie = document.cookie
            .split("; ")
            .find((row) => row.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    function showToast(message, type = "success") {
        const container = byId("employeeToastContainer");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `employee-toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        window.setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(-24px)";
            window.setTimeout(() => toast.remove(), 250);
        }, 3200);
    }

    async function ajaxPost(url) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        });

        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error("تعذر قراءة استجابة الخادم.");
        }

        if (!response.ok || !data.success) {
            throw new Error(data.message || "تعذر تنفيذ العملية.");
        }

        return data;
    }

    function updateCounters(oldActive, newActive) {
        if (oldActive === newActive) return;

        const activeCounter = byId("activeEmployeesCount");
        const inactiveCounter = byId("inactiveEmployeesCount");
        if (!activeCounter || !inactiveCounter) return;

        let active = Number.parseInt(activeCounter.textContent, 10) || 0;
        let inactive = Number.parseInt(inactiveCounter.textContent, 10) || 0;

        if (newActive) {
            active += 1;
            inactive = Math.max(0, inactive - 1);
        } else {
            active = Math.max(0, active - 1);
            inactive += 1;
        }

        activeCounter.textContent = active;
        inactiveCounter.textContent = inactive;
    }

    function statusIcon(active) {
        return active
            ? '<svg viewBox="0 0 24 24"><path d="M9 5v14M15 5v14"/></svg>'
            : '<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>';
    }

    window.toggleEmployee = async function (button) {
        const name = button.dataset.name || "الموظف";
        const wasActive = button.dataset.active === "1";
        const action = wasActive ? "تعطيل" : "تفعيل";

        if (!window.confirm(`هل تريد ${action} الموظف:\n\n${name}؟`)) return;

        const original = button.innerHTML;
        button.disabled = true;
        button.textContent = "…";

        try {
            const data = await ajaxPost(button.dataset.url);
            const isActive = Boolean(data.is_active);
            const id = button.dataset.id;
            const row = byId(`employee-row-${id}`);
            const badge = byId(`employee-status-${id}`);

            button.dataset.active = isActive ? "1" : "0";
            button.classList.remove("enable", "disable");
            button.classList.add(isActive ? "disable" : "enable");
            button.innerHTML = statusIcon(isActive);
            button.title = isActive ? "تعطيل" : "تفعيل";

            if (row) row.classList.toggle("inactive-row", !isActive);
            if (badge) {
                badge.className = `employee-system-badge ${isActive ? "active" : "inactive"}`;
                badge.innerHTML = `<span class="dot"></span>${isActive ? "نشط" : "معطل"}`;
            }

            updateCounters(wasActive, isActive);
            showToast(data.message || "تم تحديث حالة الموظف بنجاح.");
        } catch (error) {
            button.innerHTML = original;
            showToast(error.message || "تعذر تحديث حالة الموظف.", "error");
        } finally {
            button.disabled = false;
        }
    };

    window.deleteEmployee = async function (button) {
        const name = button.dataset.name || "الموظف";
        if (!window.confirm(`سيتم تعطيل الموظف بدلًا من حذفه نهائيًا:\n\n${name}\n\nهل تريد المتابعة؟`)) return;

        const original = button.innerHTML;
        button.disabled = true;
        button.textContent = "…";

        try {
            const data = await ajaxPost(button.dataset.url);
            const id = button.dataset.id;
            const row = byId(`employee-row-${id}`);
            const badge = byId(`employee-status-${id}`);
            const toggleButton = row?.querySelector("button[data-active]");
            const wasActive = toggleButton?.dataset.active === "1";

            row?.classList.add("inactive-row");

            if (badge) {
                badge.className = "employee-system-badge inactive";
                badge.innerHTML = '<span class="dot"></span>معطل';
            }

            if (toggleButton) {
                toggleButton.dataset.active = "0";
                toggleButton.classList.remove("disable");
                toggleButton.classList.add("enable");
                toggleButton.innerHTML = statusIcon(false);
                toggleButton.title = "تفعيل";
            }

            if (wasActive) updateCounters(true, false);
            showToast(data.message || "تم تعطيل الموظف بأمان.");
        } catch (error) {
            showToast(error.message || "تعذر تنفيذ التعطيل الآمن.", "error");
        } finally {
            button.disabled = false;
            button.innerHTML = original;
        }
    };

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") window.closeEmployeeDetails();
    });
})();
