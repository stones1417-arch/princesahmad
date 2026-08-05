"use strict";

/* =========================================================
   غرفة القيادة والتحكم — منصة أبواب
   خريطة الأبواب التفاعلية من 1 إلى 41

   توزيع الأبواب:
   - الجنوبية: 1–6
   - الغربية: 7–14
   - الشمالية: 15–27
   - الشرقية: 28–35
   - الجنوبية الشرقية: 36–41
========================================================= */

(function () {
    const root = document.getElementById("commandCenter");

    if (!root) {
        return;
    }

    /* =====================================================
       الإعدادات العامة
    ===================================================== */

    const refreshUrl = (
        root.dataset.refreshUrl
        || root.dataset.endpoint
        || ""
    ).trim();

    const configuredInterval = Number.parseInt(
        root.dataset.refreshInterval || "10000",
        10
    );

    const refreshInterval = Number.isFinite(configuredInterval)
        ? Math.max(configuredInterval, 5000)
        : 10000;

    let commandCenterData = null;
    let refreshTimer = null;
    let clockTimer = null;
    let doorLayoutResizeTimer = null;

    let refreshInProgress = false;
    let pageIsVisible = (
        document.visibilityState === "visible"
    );


    /* =====================================================
       إعداد قطاعات الأبواب فوق المسار المنحني

       نظام الزوايا المستخدم:
       0°   = منتصف الجهة اليمنى
       90°  = منتصف الأسفل
       180° = منتصف الجهة اليسرى
       270° = منتصف الأعلى

       تركنا فراغًا صغيرًا بين كل جهة والتي تليها
       لمنع تداخل الأبواب عند حدود الجهات.
    ===================================================== */

    const DOOR_ARC_GROUPS = [
        {
            key: "south",
            label: "الجهة الجنوبية",
            firstDoor: 1,
            lastDoor: 6,
            startAngle: 96,
            endAngle: 128,
        },
        {
            key: "west",
            label: "الجهة الغربية",
            firstDoor: 7,
            lastDoor: 14,
            startAngle: 138,
            endAngle: 198,
        },
        {
            key: "north",
            label: "الجهة الشمالية",
            firstDoor: 15,
            lastDoor: 27,
            startAngle: 208,
            endAngle: 332,
        },
        {
            key: "east",
            label: "الجهة الشرقية",
            firstDoor: 28,
            lastDoor: 35,
            startAngle: 342,
            endAngle: 404,
        },
        {
            key: "southeast",
            label: "الجهة الجنوبية الشرقية",
            firstDoor: 36,
            lastDoor: 41,
            startAngle: 50,
            endAngle: 82,
        },
    ];


    /* =====================================================
       عناصر الصفحة
    ===================================================== */

    const DOM = {
        clock: document.getElementById(
            "commandClock"
        ),

        hijriDate: document.getElementById(
            "commandHijriDate"
        ),

        gregorianDate: document.getElementById(
            "commandGregorianDate"
        ),

        shiftName: document.getElementById(
            "activeShiftName"
        ),

        shiftDate: document.getElementById(
            "activeShiftDate"
        ),

        shiftTime: document.getElementById(
            "activeShiftTime"
        ),

        shiftStatus: document.getElementById(
            "activeShiftStatus"
        ),

        operationalStatus: document.getElementById(
            "operationalStatus"
        ),

        operationalStatusLabel: document.getElementById(
            "operationalStatusLabel"
        ),

        operationalScore: document.getElementById(
            "operationalScore"
        ),

        lastUpdate: document.getElementById(
            "commandLastUpdate"
        ),

        alertsCount: document.getElementById(
            "commandAlertsCount"
        ),

        criticalAlertsCount: document.getElementById(
            "commandCriticalAlertsCount"
        ),

        warningAlertsCount: document.getElementById(
            "commandWarningAlertsCount"
        ),

        alertsList: document.getElementById(
            "commandAlertsList"
        ),

        alertsPanel: document.querySelector(
            ".command-alerts-panel"
        ),

        liveFeed: document.getElementById(
            "commandLiveFeed"
        ),

        doorMap: document.getElementById(
            "commandDoorGroups"
        ),

        doorSearchForm: document.getElementById(
            "commandDoorSearchForm"
        ),

        doorSearch: document.getElementById(
            "commandDoorSearch"
        ),

        mapDoorCount: document.getElementById(
            "commandMapDoorCount"
        ),

        wallModeButton: document.getElementById(
            "commandWallModeButton"
        ),

        doorModal: document.getElementById(
            "commandDoorModal"
        ),

        doorModalClose: document.getElementById(
            "commandDoorModalClose"
        ),

        doorModalTitle: document.getElementById(
            "commandDoorModalTitle"
        ),

        modalDoorState: document.getElementById(
            "modalDoorState"
        ),

        modalDoorDirection: document.getElementById(
            "modalDoorDirection"
        ),

        modalDoorZone: document.getElementById(
            "modalDoorZone"
        ),

        modalDoorSupervisor: document.getElementById(
            "modalDoorSupervisor"
        ),

        modalDoorEmployees: document.getElementById(
            "modalDoorEmployees"
        ),

        modalDoorMonitors: document.getElementById(
            "modalDoorMonitors"
        ),

        modalDoorIncidents: document.getElementById(
            "modalDoorIncidents"
        ),

        modalDoorMaintenance: document.getElementById(
            "modalDoorMaintenance"
        ),

        modalDoorUpdated: document.getElementById(
            "modalDoorUpdated"
        ),

        modalDoorAssignments: document.getElementById(
            "modalDoorAssignments"
        ),

        modalDoorNotes: document.getElementById(
            "modalDoorNotes"
        ),
    };


    /* =====================================================
       ربط حقول المؤشرات
    ===================================================== */

    const METRIC_IDS = {
        total_doors: "metricTotalDoors",
        maintenance_doors: "metricMaintenanceDoors",
        open_doors: "metricOpenDoors",
        closed_doors: "metricClosedDoors",
        open_maintenance: "metricOpenMaintenance",
        critical_incidents: "metricCriticalIncidents",
        assigned_employees: "metricAssignedEmployees",
        doors_without_monitor: "metricWithoutMonitor",
        doors_without_supervisor: "metricWithoutSupervisor",
    };


    const INDICATORS = {
        readiness_rate: {
            textIds: [
                "readinessRate",
                "kpiReadiness",
            ],
            barIds: [
                "readinessBar",
            ],
            circleTextId: "kpiReadiness",
        },

        supervision_coverage_rate: {
            textIds: [
                "supervisionCoverageRate",
                "kpiSupervision",
            ],
            barIds: [
                "supervisionCoverageBar",
            ],
            circleTextId: "kpiSupervision",
        },

        monitor_coverage_rate: {
            textIds: [
                "monitorCoverageRate",
                "kpiMonitorCoverage",
            ],
            barIds: [
                "monitorCoverageBar",
            ],
            circleTextId: "kpiMonitorCoverage",
        },

        operational_score: {
            textIds: [
                "summaryOperationalScore",
                "kpiOperationalScore",
            ],
            barIds: [
                "summaryOperationalBar",
            ],
            circleTextId: "kpiOperationalScore",
        },
    };


    /* =====================================================
       أدوات DOM
    ===================================================== */

    function byId(id) {
        return document.getElementById(id);
    }


    function setText(elementOrId, value) {
        const element = (
            typeof elementOrId === "string"
                ? byId(elementOrId)
                : elementOrId
        );

        if (!element) {
            return;
        }

        element.textContent = (
            value === null
            || value === undefined
                ? ""
                : String(value)
        );
    }


    function escapeHtml(value) {
        const element = document.createElement(
            "div"
        );

        element.textContent = (
            value === null
            || value === undefined
                ? ""
                : String(value)
        );

        return element.innerHTML;
    }


    function clamp(
        value,
        minimum,
        maximum
    ) {
        return Math.min(
            Math.max(value, minimum),
            maximum
        );
    }


    function normalizePercentage(value) {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return 0;
        }

        return Math.max(
            0,
            Math.min(
                Math.round(number),
                100
            )
        );
    }


    function formatNumber(value) {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "0";
        }

        return number.toLocaleString(
            "ar-SA"
        );
    }


    function parseDate(value) {
        if (!value) {
            return null;
        }

        const date = new Date(value);

        return Number.isNaN(date.getTime())
            ? null
            : date;
    }


    function formatTime(
        value,
        includeSeconds = true
    ) {
        const date = parseDate(value);

        if (!date) {
            return "غير محدد";
        }

        const options = {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        };

        if (includeSeconds) {
            options.second = "2-digit";
        }

        return date.toLocaleTimeString(
            "ar-SA",
            options
        );
    }


    function formatRelativeTime(value) {
        const date = parseDate(value);

        if (!date) {
            return "";
        }

        const difference = Math.max(
            0,
            Math.floor(
                (
                    Date.now()
                    - date.getTime()
                ) / 1000
            )
        );

        if (difference < 60) {
            return "الآن";
        }

        const minutes = Math.floor(
            difference / 60
        );

        if (minutes < 60) {
            return `منذ ${minutes} دقيقة`;
        }

        const hours = Math.floor(
            minutes / 60
        );

        if (hours < 24) {
            return `منذ ${hours} ساعة`;
        }

        const days = Math.floor(
            hours / 24
        );

        return `منذ ${days} يوم`;
    }


    function degreesToRadians(degrees) {
        return (
            Number(degrees)
            * Math.PI
        ) / 180;
    }


    /* =====================================================
       بيانات الجهات والحالات
    ===================================================== */

    function getDirectionByDoorNumber(number) {
        const doorNumber = Number(number);

        if (
            doorNumber >= 1
            && doorNumber <= 6
        ) {
            return "الجهة الجنوبية";
        }

        if (
            doorNumber >= 7
            && doorNumber <= 14
        ) {
            return "الجهة الغربية";
        }

        if (
            doorNumber >= 15
            && doorNumber <= 27
        ) {
            return "الجهة الشمالية";
        }

        if (
            doorNumber >= 28
            && doorNumber <= 35
        ) {
            return "الجهة الشرقية";
        }

        if (
            doorNumber >= 36
            && doorNumber <= 41
        ) {
            return "الجهة الجنوبية الشرقية";
        }

        return "غير مصنف";
    }


    function getStateLabel(state) {
        const labels = {
            open: "مفتوح",
            closed: "مغلق",
            maintenance: "تحت الصيانة",
            secured: "مؤمّن",
        };

        return (
            labels[state]
            || state
            || "غير محدد"
        );
    }


    function getAlertIcon(level) {
        if (level === "critical") {
            return '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20Z"></path><path d="M12 9v5M12 18h.01"></path></svg>';
        }

        if (level === "warning") {
            return '<svg viewBox="0 0 24 24"><path d="M14.7 6.3a4 4 0 0 0-5-5L12 3.6 9.6 6 7.3 3.7a4 4 0 0 0 5 5L4 17l3 3 8.3-8.3"></path></svg>';
        }

        return '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 11v6M12 7h.01"></path></svg>';
    }


    function getActivityIcon(moduleName) {
        const module = String(
            moduleName || ""
        );

        const icons = {
            "الأبواب": '<svg viewBox="0 0 24 24"><path d="M5 21h14M7 21V3h10v18M10 12h.01"></path></svg>',
            "الصيانة": '<svg viewBox="0 0 24 24"><path d="M14.7 6.3a4 4 0 0 0-5-5L12 3.6 9.6 6 7.3 3.7a4 4 0 0 0 5 5L4 17l3 3 8.3-8.3"></path></svg>',
            "البلاغات": '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20Z"></path><path d="M12 9v5M12 18h.01"></path></svg>',
            "توزيع الأبواب": '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"></circle><circle cx="17" cy="9" r="2.5"></circle><path d="M3 20c0-4 2.5-7 6-7s6 3 6 7M14 14c3.5 0 6 2.2 6 6"></path></svg>',
        };

        return icons[module] || '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v4l3 2"></path></svg>';
    }


    function getActivityClass(moduleName) {
        const classes = {
            "الصيانة": "maintenance",
            "البلاغات": "incident",
            "توزيع الأبواب": "distribution",
            "الأبواب": "doors",
        };

        return classes[String(moduleName || "")] || "system";
    }


    /* =====================================================
       تحديد القطاع وزاوية الباب
    ===================================================== */

    function getDoorArcGroup(doorNumber) {
        const number = Number(doorNumber);

        return (
            DOOR_ARC_GROUPS.find(
                function (group) {
                    return (
                        number >= group.firstDoor
                        && number <= group.lastDoor
                    );
                }
            )
            || null
        );
    }


    function calculateDoorAngle(
        doorNumber,
        group
    ) {
        const number = Number(doorNumber);

        const doorsCount = (
            group.lastDoor
            - group.firstDoor
            + 1
        );

        if (doorsCount <= 1) {
            return (
                group.startAngle
                + group.endAngle
            ) / 2;
        }

        const doorIndex = (
            number
            - group.firstDoor
        );

        const progress = (
            doorIndex
            / (doorsCount - 1)
        );

        return (
            group.startAngle
            + (
                group.endAngle
                - group.startAngle
            ) * progress
        );
    }


    function getDoorPointSize(mapWidth) {
        if (mapWidth <= 520) {
            return 26;
        }

        if (mapWidth <= 760) {
            return 30;
        }

        if (mapWidth <= 1100) {
            return 36;
        }

        if (mapWidth <= 1450) {
            return 40;
        }

        return 42;
    }


    /* =====================================================
       التوزيع الآلي للأبواب على المسار المنحني
    ===================================================== */

    function layoutDoorPoints() {
        if (!DOM.doorMap) {
            return;
        }

        const mosqueMap = DOM.doorMap.closest(
            ".command-mosque-map"
        );

        if (!mosqueMap) {
            return;
        }

        const mapWidth = mosqueMap.clientWidth;
        const mapHeight = mosqueMap.clientHeight;

        if (
            mapWidth <= 0
            || mapHeight <= 0
        ) {
            return;
        }

        const pointSize = getDoorPointSize(
            mapWidth
        );

        /*
            يجب أن تتوافق المسافة التالية تقريبًا
            مع حدود الشريط في CSS.
        */
        const horizontalPadding = Math.max(
            pointSize + 16,
            mapWidth * 0.075
        );

        const verticalPadding = Math.max(
            pointSize + 16,
            mapHeight * 0.10
        );

        const centerX = mapWidth / 2;
        const centerY = mapHeight / 2;

        const radiusX = Math.max(
            1,
            (
                mapWidth
                - horizontalPadding * 2
            ) / 2
        );

        const radiusY = Math.max(
            1,
            (
                mapHeight
                - verticalPadding * 2
            ) / 2
        );

        const doorPoints = (
            DOM.doorMap.querySelectorAll(
                ".command-door-point"
            )
        );

        doorPoints.forEach(
            function (point) {
                const doorNumber = Number(
                    point.dataset.doorNumber
                );

                const group = getDoorArcGroup(
                    doorNumber
                );

                if (!group) {
                    point.hidden = true;
                    return;
                }

                point.hidden = false;

                const angle = calculateDoorAngle(
                    doorNumber,
                    group
                );

                const radians = degreesToRadians(
                    angle
                );

                const calculatedX = (
                    centerX
                    + radiusX
                    * Math.cos(radians)
                );

                const calculatedY = (
                    centerY
                    + radiusY
                    * Math.sin(radians)
                );

                const safeX = clamp(
                    calculatedX,
                    pointSize / 2,
                    mapWidth - pointSize / 2
                );

                const safeY = clamp(
                    calculatedY,
                    pointSize / 2,
                    mapHeight - pointSize / 2
                );

                point.style.width = (
                    `${pointSize}px`
                );

                point.style.height = (
                    `${pointSize}px`
                );

                point.style.left = (
                    `${safeX}px`
                );

                point.style.top = (
                    `${safeY}px`
                );

                point.style.setProperty(
                    "--door-angle",
                    `${angle}deg`
                );

                point.style.setProperty(
                    "--door-x",
                    `${safeX}px`
                );

                point.style.setProperty(
                    "--door-y",
                    `${safeY}px`
                );
            }
        );
    }


    function scheduleDoorLayout() {
        if (doorLayoutResizeTimer) {
            window.clearTimeout(
                doorLayoutResizeTimer
            );
        }

        doorLayoutResizeTimer = window.setTimeout(
            function () {
                layoutDoorPoints();

                doorLayoutResizeTimer = null;
            },
            100
        );
    }


    /* =====================================================
       الساعة والتاريخ
    ===================================================== */

    function updateClock() {
        const now = new Date();

        setText(
            DOM.clock,
            now.toLocaleTimeString(
                "ar-SA",
                {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                    hour12: false,
                }
            )
        );

        setText(
            DOM.hijriDate,
            now.toLocaleDateString(
                "ar-SA-u-ca-islamic-umalqura",
                {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                }
            )
        );

        setText(
            DOM.gregorianDate,
            now.toLocaleDateString(
                "ar-SA",
                {
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                }
            )
        );
    }


    /* =====================================================
       المؤشرات
    ===================================================== */

    function setIndicatorValue(
        name,
        value
    ) {
        const config = INDICATORS[name];

        if (!config) {
            return;
        }

        const normalized = normalizePercentage(
            value
        );

        config.textIds.forEach(
            function (id) {
                setText(
                    id,
                    `${normalized}%`
                );
            }
        );

        config.barIds.forEach(
            function (id) {
                const bar = byId(id);

                if (bar) {
                    bar.style.width = (
                        `${normalized}%`
                    );
                }
            }
        );

        const circleText = byId(
            config.circleTextId
        );

        if (!circleText) {
            return;
        }

        const circle = circleText.closest(
            ".command-kpi-circle"
        );

        if (circle) {
            circle.style.setProperty(
                "--value",
                normalized
            );

            const card = circle.closest(
                ".command-kpi-card"
            );

            if (card) {
                const target = Number(
                    card.dataset.target || 90
                );
                const status = (
                    normalized >= target
                        ? "excellent"
                        : normalized >= Math.max(60, target - 15)
                            ? "warning"
                            : "critical"
                );
                const statusLabel = (
                    status === "excellent"
                        ? "ضمن المستهدف"
                        : status === "warning"
                            ? "يحتاج متابعة"
                            : "دون المستهدف"
                );

                card.dataset.status = status;

                const statusElement = card.querySelector(
                    ".command-kpi-status"
                );

                if (statusElement) {
                    statusElement.textContent = statusLabel;
                }
            }
        }
    }


    function renderIndicators(indicators) {
        const values = indicators || {};

        setIndicatorValue(
            "readiness_rate",
            values.readiness_rate || 0
        );

        setIndicatorValue(
            "supervision_coverage_rate",
            (
                values.supervision_coverage_rate
                ?? values.coverage_rate
                ?? 0
            )
        );

        setIndicatorValue(
            "monitor_coverage_rate",
            values.monitor_coverage_rate || 0
        );

        setIndicatorValue(
            "operational_score",
            values.operational_score || 0
        );
    }


    /* =====================================================
       الوردية والحالة التشغيلية
    ===================================================== */

    function renderShift(activeShift) {
        let shiftLabel = (
            "لا توجد وردية نشطة"
        );

        if (activeShift) {
            shiftLabel = (
                activeShift.name
                || activeShift.label
                || String(activeShift)
            );
        }

        setText(
            DOM.shiftName,
            shiftLabel
        );

        setText(
            DOM.shiftDate,
            activeShift?.date || "لا يوجد تاريخ تشغيلي"
        );

        setText(
            DOM.shiftTime,
            (
                activeShift?.start_time
                && activeShift?.end_time
                    ? `${activeShift.start_time} — ${activeShift.end_time}`
                    : "وقت الوردية غير محدد"
            )
        );

        if (DOM.shiftStatus) {
            DOM.shiftStatus.className = (
                activeShift?.status || "inactive"
            );
            setText(
                DOM.shiftStatus,
                activeShift?.status_label || "غير نشطة"
            );
        }
    }


    function renderOperationalStatus(indicators) {
        const values = indicators || {};

        const statusKey = (
            values.status_key
            || "warning"
        );

        const statusLabel = (
            values.status_label
            || "يحتاج متابعة"
        );

        const score = normalizePercentage(
            values.operational_score
        );

        if (DOM.operationalStatus) {
            DOM.operationalStatus.classList.remove(
                "stable",
                "warning",
                "critical"
            );

            DOM.operationalStatus.classList.add(
                statusKey
            );
        }

        setText(
            DOM.operationalStatusLabel,
            statusLabel
        );

        setText(
            DOM.operationalScore,
            score
        );
    }


    /* =====================================================
       بطاقات الإحصاءات
    ===================================================== */

    function renderMetrics(metrics) {
        const values = metrics || {};

        Object.entries(
            METRIC_IDS
        ).forEach(
            function ([field, id]) {
                setText(
                    id,
                    formatNumber(
                        values[field] || 0
                    )
                );
            }
        );

        const criticalMetric = document.querySelector(
            ".command-metric-card.metric-critical"
        );

        if (criticalMetric) {
            criticalMetric.dataset.alert = (
                Number(values.critical_incidents || 0) > 0
                    ? "true"
                    : "false"
            );
        }
    }


    /* =====================================================
       التنبيهات
    ===================================================== */

    function renderAlerts(alerts) {
        const items = Array.isArray(alerts)
            ? alerts
            : [];

        setText(
            DOM.alertsCount,
            `${items.length} تنبيه`
        );

        setText(
            DOM.criticalAlertsCount,
            `${items.filter((item) => item.level === "critical").length} حرج`
        );

        setText(
            DOM.warningAlertsCount,
            `${items.filter((item) => item.level === "warning").length} متابعة`
        );

        if (!DOM.alertsList) {
            return;
        }

        if (!items.length) {
            DOM.alertsList.innerHTML = `
                <div class="command-empty-state">
                    لا توجد تنبيهات حالية.
                </div>
            `;

            return;
        }

        DOM.alertsList.innerHTML = items
            .map(
                function (alert) {
                    const level = (
                        alert.level
                        || "info"
                    );

                    const levelLabel = (
                        level === "critical"
                            ? "أولوية حرجة"
                            : level === "warning"
                                ? "تحتاج متابعة"
                                : "تنبيه معلوماتي"
                    );

                    const title = String(
                        alert.title || ""
                    );
                    const panel = DOM.alertsPanel;
                    const actionUrl = (
                        level === "critical"
                            ? panel?.dataset.incidentsUrl
                            : title.includes("صيانة")
                                ? panel?.dataset.maintenanceUrl
                                : panel?.dataset.distributionUrl
                    ) || "#";

                    return `
                        <article
                            class="
                                command-alert-item
                                ${escapeHtml(level)}
                            "
                        >
                            <div class="command-alert-main">

                                <span class="command-alert-icon">
                                    ${getAlertIcon(level)}
                                </span>

                                <div class="command-alert-content">

                                    <span class="command-alert-level">
                                        ${levelLabel}
                                    </span>

                                    <strong>
                                        ${escapeHtml(
                                            alert.title
                                            || "تنبيه تشغيلي"
                                        )}
                                    </strong>

                                    <p>
                                        ${escapeHtml(
                                            alert.message
                                            || ""
                                        )}
                                    </p>

                                </div>

                            </div>

                            <a class="command-alert-action" href="${escapeHtml(actionUrl)}">
                                فتح المعالجة
                                <span aria-hidden="true">←</span>
                            </a>
                        </article>
                    `;
                }
            )
            .join("");
    }


    /* =====================================================
       سجل العمليات المباشرة
    ===================================================== */

    function renderLiveFeed(items) {
        const feedItems = Array.isArray(items)
            ? items
            : [];

        if (!DOM.liveFeed) {
            return;
        }

        if (!feedItems.length) {
            DOM.liveFeed.innerHTML = `
                <div class="command-empty-state">
                    لا توجد عمليات مباشرة حاليًا.
                </div>
            `;

            return;
        }

        DOM.liveFeed.innerHTML = feedItems
            .map(
                function (item) {
                    return `
                        <article class="command-live-feed-item ${getActivityClass(item.module)}">

                            <span class="command-live-feed-icon">
                                ${getActivityIcon(item.module)}
                            </span>

                            <div class="command-live-feed-content">

                                <span class="command-live-feed-module">
                                    ${escapeHtml(item.module || "النظام")}
                                </span>

                                <strong>
                                    ${escapeHtml(
                                        item.description
                                        || ""
                                    )}
                                </strong>

                                <p><span>المنفّذ:</span>
                                    ${escapeHtml(
                                        item.username
                                        || "النظام"
                                    )}
                                </p>

                            </div>

                            <div class="command-live-feed-time">
                                <time title="${escapeHtml(item.created_at || "")}">
                                    منذ ${escapeHtml(formatRelativeTime(item.created_at))}
                                </time>
                                <small>#${escapeHtml(item.id || "—")}</small>
                            </div>

                        </article>
                    `;
                }
            )
            .join("");
    }


    /* =====================================================
       تجهيز بيانات الأبواب
    ===================================================== */

    function normalizeDoor(
        door,
        groupLabel = ""
    ) {
        const number = Number(
            door.number
            ?? door.door_number
            ?? door.id
        );

        const state = (
            door.state
            || "closed"
        );

        return {
            ...door,

            id: (
                door.id
                ?? door.door_id
                ?? number
            ),

            number,

            state,

            state_label: (
                door.state_label
                || getStateLabel(state)
            ),

            direction: (
                groupLabel
                || door.direction
                || door.direction_label
                || getDirectionByDoorNumber(number)
            ),

            zone: (
                door.zone_name
                || door.zone
                || ""
            ),

            supervisor_name: (
                door.supervisor_name
                || door.supervisor
                || ""
            ),

            employee_count: Number(
                door.employee_count || 0
            ),

            monitor_count: Number(
                door.monitor_count || 0
            ),

            incident_count: Number(
                door.incident_count || 0
            ),

            maintenance_count: Number(
                door.maintenance_count || 0
            ),

            assignments: Array.isArray(
                door.assignments
            )
                ? door.assignments
                : [],
        };
    }


    function getAllDoors(groups) {
        const result = [];

        (
            Array.isArray(groups)
                ? groups
                : []
        ).forEach(
            function (group) {
                const label = (
                    group.label
                    || group.direction_label
                    || ""
                );

                (
                    Array.isArray(group.doors)
                        ? group.doors
                        : []
                ).forEach(
                    function (door) {
                        const normalizedDoor = normalizeDoor(
                            door,
                            label
                        );

                        if (
                            normalizedDoor.number >= 1
                            && normalizedDoor.number <= 41
                        ) {
                            result.push(
                                normalizedDoor
                            );
                        }
                    }
                );
            }
        );

        return result.sort(
            function (firstDoor, secondDoor) {
                return (
                    firstDoor.number
                    - secondDoor.number
                );
            }
        );
    }


    /* =====================================================
       إنشاء نقطة الباب
    ===================================================== */

    function createDoorPointHtml(door) {
        const number = escapeHtml(
            door.number
        );

        const state = escapeHtml(
            door.state
        );

        const stateLabel = escapeHtml(
            door.state_label
        );

        const direction = escapeHtml(
            door.direction
        );

        const doorId = escapeHtml(
            door.id
        );

        return `
            <button
                type="button"
                class="
                    command-door-point
                    state-${state}
                    door-point-${number}
                "
                data-door-id="${doorId}"
                data-door-number="${number}"
                data-direction="${direction}"
                data-state="${state}"
                data-state-label="${stateLabel}"
                aria-label="
                    عرض معلومات الباب
                    ${number}
                "
                title="
                    باب ${number}
                    — ${direction}
                    — ${stateLabel}
                "
            >
                <span>
                    ${number}
                </span>
            </button>
        `;
    }


    function renderDoorMap(groups) {
        if (!DOM.doorMap) {
            return;
        }

        const doors = getAllDoors(groups);

        setText(
            DOM.mapDoorCount,
            formatNumber(doors.length)
        );

        DOM.doorMap.innerHTML = doors
            .map(createDoorPointHtml)
            .join("");

        /*
            يجب الانتظار حتى يُدرج المتصفح جميع النقاط
            داخل الصفحة، ثم تُحسب المواقع.
        */
        window.requestAnimationFrame(
            function () {
                layoutDoorPoints();
            }
        );
    }


    /* =====================================================
       البحث عن باب
    ===================================================== */

    function findDoorById(doorId) {
        if (!commandCenterData) {
            return null;
        }

        const groups = Array.isArray(
            commandCenterData.groups
        )
            ? commandCenterData.groups
            : [];

        for (const group of groups) {
            const direction = (
                group.label
                || group.direction_label
                || ""
            );

            const groupDoors = Array.isArray(
                group.doors
            )
                ? group.doors
                : [];

            const matchingDoor = groupDoors.find(
                function (door) {
                    const currentId = (
                        door.id
                        ?? door.door_id
                        ?? door.number
                        ?? door.door_number
                    );

                    return (
                        String(currentId)
                        === String(doorId)
                    );
                }
            );

            if (matchingDoor) {
                return normalizeDoor(
                    matchingDoor,
                    direction
                );
            }
        }

        return null;
    }


    /* =====================================================
       نافذة تفاصيل الباب
    ===================================================== */

    function renderDoorAssignments(assignments) {
        if (!DOM.modalDoorAssignments) {
            return;
        }

        const items = Array.isArray(assignments)
            ? assignments
            : [];

        if (!items.length) {
            DOM.modalDoorAssignments.innerHTML = `
                <div class="command-empty-state">
                    لا توجد توزيعات على الباب.
                </div>
            `;

            return;
        }

        DOM.modalDoorAssignments.innerHTML = items
            .map(
                function (assignment) {
                    const employeeName = (
                        assignment.employee_name
                        || assignment.full_name
                        || assignment.employee
                        || "موظف غير محدد"
                    );

                    const employeeNumber = (
                        assignment.employee_number
                        || ""
                    );

                    const role = (
                        assignment.role_label
                        || assignment.role
                        || "غير محدد"
                    );

                    return `
                        <article
                            class="
                                command-door-assignment-item
                            "
                        >
                            <div>

                                <strong>
                                    ${escapeHtml(
                                        employeeName
                                    )}
                                </strong>

                                <small>
                                    ${escapeHtml(
                                        employeeNumber
                                    )}
                                </small>

                            </div>

                            <span>
                                ${escapeHtml(role)}
                            </span>

                        </article>
                    `;
                }
            )
            .join("");
    }


    function openDoorModal(doorId) {
        const door = findDoorById(doorId);

        if (
            !door
            || !DOM.doorModal
        ) {
            return;
        }

        DOM.doorModal.dataset.doorId = (
            door.id
        );

        DOM.doorModal.dataset.state = (
            door.state || "unknown"
        );

        setText(
            DOM.doorModalTitle,
            `باب ${door.number}`
        );

        setText(
            DOM.modalDoorState,
            door.state_label
        );

        setText(
            DOM.modalDoorDirection,
            door.direction
        );

        setText(
            DOM.modalDoorZone,
            door.zone || "غير محددة"
        );

        setText(
            DOM.modalDoorSupervisor,
            (
                door.supervisor_name
                || "غير معيّن"
            )
        );

        setText(
            DOM.modalDoorEmployees,
            formatNumber(
                door.employee_count
            )
        );

        setText(
            DOM.modalDoorMonitors,
            formatNumber(
                door.monitor_count
            )
        );

        setText(
            DOM.modalDoorIncidents,
            formatNumber(
                door.incident_count
            )
        );

        setText(
            DOM.modalDoorMaintenance,
            formatNumber(
                door.maintenance_count
            )
        );

        setText(
            DOM.modalDoorUpdated,
            formatTime(
                door.updated_at,
                false
            )
        );

        setText(
            DOM.modalDoorNotes,
            (
                door.notes
                || "لا توجد ملاحظات."
            )
        );

        renderDoorAssignments(
            door.assignments
        );

        DOM.doorModal.classList.add(
            "open"
        );

        DOM.doorModal.setAttribute(
            "aria-hidden",
            "false"
        );

        document.body.classList.add(
            "command-modal-open"
        );

        if (DOM.doorModalClose) {
            DOM.doorModalClose.focus();
        }
    }


    function closeDoorModal() {
        if (!DOM.doorModal) {
            return;
        }

        DOM.doorModal.classList.remove(
            "open"
        );

        DOM.doorModal.setAttribute(
            "aria-hidden",
            "true"
        );

        delete DOM.doorModal.dataset.doorId;

        document.body.classList.remove(
            "command-modal-open"
        );
    }


    function refreshOpenDoorModal() {
        if (
            !DOM.doorModal
            || !DOM.doorModal.classList.contains(
                "open"
            )
        ) {
            return;
        }

        const doorId = (
            DOM.doorModal.dataset.doorId
        );

        if (doorId) {
            openDoorModal(doorId);
        }
    }


    /* =====================================================
       جلب بيانات غرفة القيادة
    ===================================================== */

    async function loadCommandCenterData() {
        if (
            refreshInProgress
            || !refreshUrl
            || !pageIsVisible
        ) {
            return;
        }

        refreshInProgress = true;

        root.classList.add(
            "is-refreshing"
        );

        try {
            const response = await fetch(
                refreshUrl,
                {
                    method: "GET",

                    credentials: "same-origin",

                    cache: "no-store",

                    headers: {
                        "Accept": "application/json",

                        "X-Requested-With": (
                            "XMLHttpRequest"
                        ),
                    },
                }
            );

            if (!response.ok) {
                throw new Error(
                    `فشل تحميل البيانات: ${response.status}`
                );
            }

            const data = await response.json();

            if (
                !data
                || data.success !== true
            ) {
                throw new Error(
                    "استجابة غرفة القيادة غير صحيحة."
                );
            }

            commandCenterData = data;

            renderCommandCenter(data);

            root.classList.remove(
                "has-refresh-error"
            );
        } catch (error) {
            console.error(
                "Command center refresh error:",
                error
            );

            root.classList.add(
                "has-refresh-error"
            );
        } finally {
            refreshInProgress = false;

            root.classList.remove(
                "is-refreshing"
            );
        }
    }


    /* =====================================================
       العرض الكامل
    ===================================================== */

    function renderCommandCenter(data) {
        renderShift(
            data.active_shift
        );

        renderOperationalStatus(
            data.indicators || {}
        );

        renderMetrics(
            data.metrics || {}
        );

        renderIndicators(
            data.indicators || {}
        );

        renderAlerts(
            data.alerts || []
        );

        renderDoorMap(
            data.groups || []
        );

        renderLiveFeed(
            data.live_feed || []
        );

        setText(
            DOM.lastUpdate,
            formatTime(
                data.generated_at
            )
        );

        refreshOpenDoorModal();
    }


    /* =====================================================
       وضع شاشة غرفة العمليات
    ===================================================== */

    function updateWallModeButton(enabled) {
        if (!DOM.wallModeButton) {
            return;
        }

        const label = (
            DOM.wallModeButton.querySelector(
                "strong"
            )
        );

        const icon = (
            DOM.wallModeButton.querySelector(
                "span"
            )
        );

        if (label) {
            label.textContent = enabled
                ? "إنهاء وضع الغرفة"
                : "وضع الغرفة";
        }

        if (icon) {
            icon.textContent = enabled
                ? "✕"
                : "▣";
        }

        DOM.wallModeButton.setAttribute(
            "aria-pressed",
            enabled ? "true" : "false"
        );
    }


    function toggleWallMode() {
        const enabled = root.classList.toggle(
            "wall-mode"
        );

        try {
            window.localStorage.setItem(
                "abwaab-command-wall-mode",
                enabled ? "1" : "0"
            );
        } catch (error) {
            console.warn(
                "تعذر حفظ وضع الغرفة.",
                error
            );
        }

        updateWallModeButton(enabled);

        /*
            حجم الخريطة يتغير عند تشغيل وضع الغرفة،
            لذلك يجب إعادة حساب مواضع الأبواب.
        */
        window.requestAnimationFrame(
            function () {
                layoutDoorPoints();
            }
        );
    }


    function restoreWallMode() {
        let enabled = false;

        try {
            enabled = (
                window.localStorage.getItem(
                    "abwaab-command-wall-mode"
                ) === "1"
            );
        } catch (error) {
            enabled = false;
        }

        root.classList.toggle(
            "wall-mode",
            enabled
        );

        updateWallModeButton(enabled);
    }


    /* =====================================================
       الأحداث
    ===================================================== */

    function bindEvents() {
        document.addEventListener(
            "click",
            function (event) {
                const doorPoint = event.target.closest(
                    ".command-door-point"
                );

                if (
                    doorPoint
                    && root.contains(doorPoint)
                ) {
                    openDoorModal(
                        doorPoint.dataset.doorId
                    );

                    return;
                }

                const closeTarget = event.target.closest(
                    "[data-close-door-modal]"
                );

                if (closeTarget) {
                    closeDoorModal();
                }
            }
        );

        if (DOM.doorModalClose) {
            DOM.doorModalClose.addEventListener(
                "click",
                closeDoorModal
            );
        }

        if (DOM.wallModeButton) {
            DOM.wallModeButton.addEventListener(
                "click",
                toggleWallMode
            );
        }

        if (DOM.doorSearchForm) {
            DOM.doorSearchForm.addEventListener(
                "submit",
                function (event) {
                    event.preventDefault();

                    const doorNumber = Number(
                        DOM.doorSearch?.value
                    );
                    const doorPoint = DOM.doorMap?.querySelector(
                        `.door-point-${doorNumber}`
                    );

                    DOM.doorMap?.querySelectorAll(
                        ".command-door-point.selected"
                    ).forEach((point) => point.classList.remove("selected"));

                    if (doorPoint) {
                        doorPoint.classList.add("selected");
                        doorPoint.focus();
                        openDoorModal(doorPoint.dataset.doorId);
                        DOM.doorSearch?.setCustomValidity("");
                    } else if (DOM.doorSearch) {
                        DOM.doorSearch.setCustomValidity("رقم الباب غير موجود في الخريطة الحالية.");
                        DOM.doorSearch.reportValidity();
                    }
                }
            );

            DOM.doorSearch?.addEventListener(
                "input",
                function () {
                    DOM.doorSearch.setCustomValidity("");
                }
            );
        }

        document.addEventListener(
            "keydown",
            function (event) {
                if (event.key === "Escape") {
                    closeDoorModal();
                }
            }
        );

        document.addEventListener(
            "visibilitychange",
            function () {
                pageIsVisible = (
                    document.visibilityState
                    === "visible"
                );

                if (pageIsVisible) {
                    loadCommandCenterData();

                    window.requestAnimationFrame(
                        function () {
                            layoutDoorPoints();
                        }
                    );
                }
            }
        );

        window.addEventListener(
            "resize",
            scheduleDoorLayout,
            {
                passive: true,
            }
        );

        window.addEventListener(
            "orientationchange",
            scheduleDoorLayout
        );

        window.addEventListener(
            "online",
            loadCommandCenterData
        );

        window.addEventListener(
            "beforeunload",
            stopTimers
        );

        /*
            إعادة الحساب بعد اكتمال تحميل الصور والخطوط.
        */
        window.addEventListener(
            "load",
            function () {
                window.requestAnimationFrame(
                    function () {
                        layoutDoorPoints();
                    }
                );
            }
        );
    }


    /* =====================================================
       المؤقتات
    ===================================================== */

    function startRefreshTimer() {
        stopRefreshTimer();

        refreshTimer = window.setInterval(
            loadCommandCenterData,
            refreshInterval
        );
    }


    function stopRefreshTimer() {
        if (!refreshTimer) {
            return;
        }

        window.clearInterval(
            refreshTimer
        );

        refreshTimer = null;
    }


    function startClockTimer() {
        if (clockTimer) {
            window.clearInterval(
                clockTimer
            );
        }

        updateClock();

        clockTimer = window.setInterval(
            updateClock,
            1000
        );
    }


    function stopClockTimer() {
        if (!clockTimer) {
            return;
        }

        window.clearInterval(
            clockTimer
        );

        clockTimer = null;
    }


    function stopDoorLayoutTimer() {
        if (!doorLayoutResizeTimer) {
            return;
        }

        window.clearTimeout(
            doorLayoutResizeTimer
        );

        doorLayoutResizeTimer = null;
    }


    function stopTimers() {
        stopRefreshTimer();
        stopClockTimer();
        stopDoorLayoutTimer();
    }


    /* =====================================================
       تشغيل الصفحة
    ===================================================== */

    function initialize() {
        startClockTimer();

        restoreWallMode();

        bindEvents();

        /*
            ترتيب الأبواب الموجودة من قالب Django
            قبل وصول أول تحديث JSON.
        */
        window.requestAnimationFrame(
            function () {
                layoutDoorPoints();
            }
        );

        loadCommandCenterData();

        startRefreshTimer();
    }


    initialize();

})();
