/**
 * Direct Cash Flow — Query Report JS
 * App    : armada / armada_custom_app
 * Frappe : v15
 *
 * Features:
 *  1. PDF Export button  — landscape A4 via server-side wkhtmltopdf
 *  2. Category Reorder   — Drag-and-drop dialog (SortableJS, Frappe v15 built-in)
 *                          Persists to DB via save_category_order()
 *                          Visible to all, editable only by kassa admin / Accounts Manager / System Manager
 */

frappe.query_reports["Direct Cash Flow"] = {

    // -------------------------------------------------------------------------
    // FILTERS
    // -------------------------------------------------------------------------
    filters: [
        {
            fieldname: "company",
            label:     __("Company"),
            fieldtype: "Link",
            options:   "Company",
            reqd:      1,
            default:   frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "from_date",
            label:     __("From Date"),
            fieldtype: "Date",
            reqd:      1,
            default:   frappe.datetime.year_start(),
        },
        {
            fieldname: "to_date",
            label:     __("To Date"),
            fieldtype: "Date",
            reqd:      1,
            default:   frappe.datetime.nowdate(),
        },
        {
            fieldname: "display_type",
            label:     __("Display Type"),
            fieldtype: "Select",
            options:   "Monthly\nQuarterly\nWeekly\nDaily",
            default:   "Monthly",
            reqd:      1,
        },
        {
            fieldname: "party_type",
            label:     __("Party Type"),
            fieldtype: "Link",
            options:   "Party Type",
            reqd:      0,
        },
    ],

    // -------------------------------------------------------------------------
    // ON LOAD — inject buttons + global drag styles
    // -------------------------------------------------------------------------
    onload: function (report) {

        // ── Global drag-and-drop CSS (injected once) ──────────────────────
        if (!document.getElementById("cf-dnd-styles")) {
            const style = document.createElement("style");
            style.id    = "cf-dnd-styles";
            style.textContent = `
                /* Ghost (dragging clone) */
                .cf-drag-ghost {
                    opacity       : 0.35 !important;
                    background    : #FEF9E7 !important;
                    border-left   : 3px solid #E67E22 !important;
                }
                /* Chosen (the item being held) */
                .cf-drag-chosen {
                    box-shadow    : 0 4px 16px rgba(0,0,0,0.18) !important;
                    border-radius : 4px !important;
                    background    : #FFFDE7 !important;
                    cursor        : grabbing !important;
                }
                /* Drop target highlight */
                .cf-sortable-list.cf-drag-over {
                    background    : #FFF8E1;
                    border-color  : #F0A500 !important;
                    transition    : background 0.15s;
                }
                /* Handle icon pulse on hover */
                .cf-drag-handle:hover {
                    color         : #E67E22 !important;
                    transform     : scale(1.15);
                    transition    : transform 0.1s, color 0.1s;
                }
                /* Smooth row transitions during sort */
                .cf-sort-item {
                    transition    : background 0.15s ease;
                }
                .cf-sort-item:hover {
                    background    : #FEF9E7 !important;
                }
            `;
            document.head.appendChild(style);
        }

        // ── PDF Export button ─────────────────────────────────────────────
        report.page.add_inner_button(__("Экспорт PDF"), function () {
            _export_pdf(report);
        });

        // ── Category Reorder button ───────────────────────────────────────
        report.page.add_inner_button(__("⠿ Порядок категорий"), function () {
            _open_reorder_dialog(report);
        });
    },

    // -------------------------------------------------------------------------
    // CELL FORMATTER
    // -------------------------------------------------------------------------
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        const fieldname = column.fieldname;
        const raw       = (data[fieldname] !== undefined) ? data[fieldname] : null;

        function fmtRounded(num) {
            return Math.abs(Math.round(num)).toLocaleString("ru-RU", {
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
            });
        }

        // ── Activity header rows ──
        if (data.is_activity_header) {
            if (column.fieldtype === "Currency" && raw !== null) {
                const v = parseFloat(raw);
                if (!isNaN(v)) {
                    value = v === 0
                        ? `<span style="font-weight:700;">0</span>`
                        : v < 0
                            ? `<span style="font-weight:700;">(${fmtRounded(v)})</span>`
                            : `<span style="font-weight:700;">${fmtRounded(v)}</span>`;
                }
            } else {
                value = `<span style="font-weight:700;color:#c0392b;">${value || ""}</span>`;
            }
        }

        // ── Balance rows ──
        if (data.is_balance_row) {
            if (column.fieldtype === "Currency" && raw !== null) {
                const v = parseFloat(raw);
                if (!isNaN(v)) {
                    value = v === 0
                        ? `<span style="font-weight:700;">0</span>`
                        : v < 0
                            ? `<span style="font-weight:700;">(${fmtRounded(v)})</span>`
                            : `<span style="font-weight:700;">${fmtRounded(v)}</span>`;
                }
            } else {
                value = `<span style="font-weight:700;">${value || ""}</span>`;
            }
        }

        // ── Subtotal rows ──
        if (data.is_subtotal) {
            if (column.fieldtype === "Currency" && raw !== null) {
                const v = parseFloat(raw);
                if (!isNaN(v)) {
                    value = v === 0
                        ? `<span style="font-weight:600;">0</span>`
                        : v < 0
                            ? `<span style="font-weight:600;">(${fmtRounded(v)})</span>`
                            : `<span style="font-weight:600;">${fmtRounded(v)}</span>`;
                }
            } else {
                value = `<span style="font-weight:600;">${value || ""}</span>`;
            }
        }

        // ── Data rows ──
        if (data.row_type === "data") {
            const isInflow = data.is_inflow === 1;

            if (fieldname === "label") {
                const lbl    = (data.label || "").trim();
                const prefix = isInflow ? "+" : "-";
                const color  = isInflow ? "#27AE60" : "#C0392B";
                value = `<span style="color:${color};font-weight:700;">${prefix} ${frappe.utils.escape_html(lbl)}</span>`;
            }

            if (column.fieldtype === "Currency" && raw !== null) {
                const v = parseFloat(raw);
                if (!isNaN(v)) {
                    if (v === 0) {
                        value = `<span style="color:#1C2833;font-weight:700;">0</span>`;
                    } else if (v < 0) {
                        value = `<span style="color:#C0392B;font-weight:700;">(${fmtRounded(v)})</span>`;
                    } else {
                        value = `<span style="color:#27AE60;font-weight:700;">${fmtRounded(v)}</span>`;
                    }
                }
            }
        }

        return value;
    },
};


// =============================================================================
// PRIVATE — PDF EXPORT
// =============================================================================

function _export_pdf(report) {
    const filters = report.get_values();
    if (!filters) {
        frappe.msgprint(__("Пожалуйста, заполните фильтры перед экспортом."));
        return;
    }

    frappe.show_alert({ message: __("Генерация PDF…"), indicator: "orange" });

    frappe.call({
        method:        "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.export_pdf",
        args:          { filters: JSON.stringify(filters) },
        freeze:        true,
        freeze_message: __("Генерация PDF, пожалуйста подождите…"),

        callback: function (r) {
            if (!r.message) {
                frappe.show_alert({ message: __("Ошибка: пустой ответ."), indicator: "red" });
                return;
            }
            try {
                const byteChars = atob(r.message);
                const bytes     = new Uint8Array(byteChars.length);
                for (let i = 0; i < byteChars.length; i++) {
                    bytes[i] = byteChars.charCodeAt(i);
                }
                const blob     = new Blob([bytes], { type: "application/pdf" });
                const url      = URL.createObjectURL(blob);
                const company  = (filters.company || "report").replace(/\s+/g, "_");
                const filename = `Direct_Cash_Flow_${company}_${filters.from_date}_${filters.to_date}.pdf`;

                const a       = document.createElement("a");
                a.href        = url;
                a.download    = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(url), 5000);

                frappe.show_alert({ message: __("PDF успешно скачан."), indicator: "green" });
            } catch (err) {
                console.error("PDF decode error:", err);
                frappe.show_alert({ message: __("Ошибка при обработке PDF."), indicator: "red" });
            }
        },
        error: function (err) {
            console.error("PDF export error:", err);
            frappe.show_alert({ message: __("Серверная ошибка."), indicator: "red" });
        },
    });
}


// =============================================================================
// PRIVATE — CATEGORY REORDER DIALOG
// =============================================================================

const CF_ACTIVITY_ORDER = [
    "Операционная деятельность",
    "Инвестиционная деятельность",
    "Финансовая деятельность",
];

const CF_ACTIVITY_META = {
    "Операционная деятельность":   { color: "#E67E22", icon: "💼" },
    "Инвестиционная деятельность": { color: "#2980B9", icon: "📈" },
    "Финансовая деятельность":     { color: "#27AE60", icon: "🏦" },
};

// Tracks live Sortable instances so we can destroy them on dialog hide
let _sortableInstances = [];


function _open_reorder_dialog(report) {
    frappe.call({
        method: "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.get_categories_for_reorder",

        callback: function (r) {
            if (!r.message) {
                frappe.show_alert({ message: __("Не удалось загрузить категории."), indicator: "red" });
                return;
            }
            _render_reorder_dialog(r.message.categories, r.message.can_reorder, report);
        },

        error: function () {
            frappe.show_alert({ message: __("Серверная ошибка при загрузке категорий."), indicator: "red" });
        },
    });
}


function _render_reorder_dialog(categories, canReorder, report) {

    // ── Group categories by activity ──────────────────────────────────────
    const grouped = {};
    CF_ACTIVITY_ORDER.forEach(act => { grouped[act] = []; });
    categories.forEach(cat => {
        if (grouped[cat.activity_type] !== undefined) {
            grouped[cat.activity_type].push(cat);
        }
    });

    // ── Build dialog HTML ─────────────────────────────────────────────────
    const readonlyBanner = canReorder ? "" : `
        <div style="
            background   : #FFF3CD;
            border       : 1px solid #F0AD4E;
            border-radius: 4px;
            padding      : 8px 12px;
            margin-bottom: 12px;
            font-size    : 12px;
            color        : #856404;
            display      : flex;
            align-items  : center;
            gap          : 8px;
        ">
            <span style="font-size:15px;">🔒</span>
            <span>${__("У вас нет прав на изменение порядка. Отображение только для просмотра.")}</span>
        </div>`;

    let groupsHtml = "";

    CF_ACTIVITY_ORDER.forEach(act => {
        const items = grouped[act] || [];
        const meta  = CF_ACTIVITY_META[act] || { color: "#888", icon: "•" };

        const itemsHtml = items.map((cat, idx) => `
            <li
                class        = "cf-sort-item"
                data-name    = "${frappe.utils.escape_html(cat.name)}"
                data-activity= "${frappe.utils.escape_html(act)}"
                style        = "
                    display        : flex;
                    align-items    : center;
                    padding        : 9px 12px;
                    border-bottom  : 1px solid #F0F0F0;
                    background     : ${idx % 2 === 0 ? "#FFFFFF" : "#FAFAFA"};
                    cursor         : ${canReorder ? "grab" : "default"};
                    user-select    : none;
                    list-style     : none;
                "
            >
                ${canReorder ? `
                <span
                    class = "cf-drag-handle"
                    title = "${__("Перетащить")}"
                    style = "
                        color       : #BDC3C7;
                        font-size   : 16px;
                        margin-right: 10px;
                        flex-shrink : 0;
                        line-height : 1;
                        cursor      : grab;
                    "
                >⠿</span>` : `
                <span style="color:#BDC3C7;margin-right:10px;flex-shrink:0;">
                    ${idx + 1}.
                </span>`}
                <span style="
                    flex       : 1;
                    font-size  : 12px;
                    font-weight: 500;
                    color      : #2C3E50;
                ">
                    ${frappe.utils.escape_html(cat.category_name)}
                </span>
                ${canReorder ? `
                <span style="
                    font-size  : 10px;
                    color      : #BDC3C7;
                    margin-left: 8px;
                    flex-shrink: 0;
                ">drag</span>` : ""}
            </li>`
        ).join("");

        groupsHtml += `
            <div style="margin-bottom:16px; border-radius:6px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,0.08);">

                <!-- Activity header -->
                <div style="
                    background   : ${meta.color};
                    color        : #FFFFFF;
                    font-weight  : 700;
                    font-size    : 12px;
                    padding      : 8px 14px;
                    display      : flex;
                    align-items  : center;
                    gap          : 8px;
                    letter-spacing: 0.3px;
                ">
                    <span>${meta.icon}</span>
                    <span>${frappe.utils.escape_html(act)}</span>
                    <span style="
                        margin-left  : auto;
                        font-size    : 10px;
                        font-weight  : 400;
                        opacity      : 0.85;
                        background   : rgba(255,255,255,0.2);
                        padding      : 1px 7px;
                        border-radius: 10px;
                    ">${items.length} ${__("категорий")}</span>
                </div>

                <!-- Sortable list -->
                <ul
                    id    = "cf-list-${_slugify(act)}"
                    class = "cf-sortable-list"
                    data-activity = "${frappe.utils.escape_html(act)}"
                    style = "
                        margin       : 0;
                        padding      : 0;
                        border       : 1px solid #E8E8E8;
                        border-top   : none;
                        border-radius: 0 0 6px 6px;
                        background   : #FFFFFF;
                        min-height   : 40px;
                    "
                >
                    ${itemsHtml || `<li style="padding:12px;color:#BDC3C7;font-size:12px;text-align:center;list-style:none;">
                        ${__("Нет категорий в этой группе")}
                    </li>`}
                </ul>
            </div>`;
    });

    const dialogBody = `
        <div id="cf-reorder-root" style="padding:4px 2px;">
            ${readonlyBanner}
            ${canReorder ? `
            <div style="
                background   : #EBF5FB;
                border       : 1px solid #AED6F1;
                border-radius: 4px;
                padding      : 7px 12px;
                margin-bottom: 14px;
                font-size    : 11px;
                color        : #1A5276;
                display      : flex;
                align-items  : center;
                gap          : 8px;
            ">
                <span style="font-size:14px;">💡</span>
                <span>${__("Перетащите строки внутри каждой группы. Между группами перемещение недоступно.")}</span>
            </div>` : ""}
            ${groupsHtml}
        </div>`;

    // ── Create dialog ─────────────────────────────────────────────────────
    const dlg = new frappe.ui.Dialog({
        title:                __("Порядок отображения категорий"),
        size:                 "large",
        fields: [{
            fieldtype: "HTML",
            fieldname: "reorder_body",
            options:   dialogBody,
        }],
        primary_action_label: canReorder ? __("💾 Сохранить порядок") : __("Закрыть"),
        primary_action: function () {
            if (!canReorder) { dlg.hide(); return; }
            _save_order(dlg, report);
        },
    });

    dlg.show();

    // ── Activate SortableJS (only for users with write permission) ────────
    if (canReorder) {
        _activate_sortable(dlg);
    }

    // ── Destroy Sortable instances when dialog closes ─────────────────────
    dlg.$wrapper.on("hide.bs.modal", function () {
        _sortableInstances.forEach(s => { try { s.destroy(); } catch (_) {} });
        _sortableInstances = [];
    });
}


function _activate_sortable(dlg) {
    // Frappe v15 bundles SortableJS — available as window.Sortable
    // If for any reason it's not loaded yet, we retry once after 300 ms.

    const _init = () => {
        const lists = dlg.$wrapper[0].querySelectorAll(".cf-sortable-list");

        lists.forEach(ul => {
            const activity = ul.dataset.activity;

            const sortable = new Sortable(ul, {
                animation    : 180,
                easing       : "cubic-bezier(0.25, 1, 0.5, 1)",
                handle       : ".cf-drag-handle",
                ghostClass   : "cf-drag-ghost",
                chosenClass  : "cf-drag-chosen",
                dragClass    : "cf-drag-chosen",

                // Each list is its own isolated group — no cross-activity moves
                group: {
                    name: `cf-group-${activity}`,
                    pull: false,
                    put:  false,
                },

                onStart: function (evt) {
                    evt.item.style.opacity = "0.7";
                    ul.classList.add("cf-drag-over");
                },
                onEnd: function (evt) {
                    evt.item.style.opacity = "1";
                    ul.classList.remove("cf-drag-over");

                    // Re-stripe row backgrounds after reorder
                    _restripe(ul);
                },
            });

            _sortableInstances.push(sortable);
        });
    };

    if (typeof Sortable !== "undefined") {
        _init();
    } else {
        // Fallback: wait one tick for Frappe bundle to load
        setTimeout(() => {
            if (typeof Sortable !== "undefined") {
                _init();
            } else {
                frappe.show_alert({
                    message  : __("SortableJS не загружен. Перезагрузите страницу."),
                    indicator: "orange",
                });
            }
        }, 400);
    }
}


function _save_order(dlg, report) {
    // Collect new order from all groups in CF_ACTIVITY_ORDER sequence
    const orderedNames = [];

    CF_ACTIVITY_ORDER.forEach(act => {
        const ul = dlg.$wrapper[0].querySelector(
            `.cf-sortable-list[data-activity="${CSS.escape(act)}"]`
        );
        if (!ul) return;

        ul.querySelectorAll("li[data-name]").forEach(li => {
            orderedNames.push(li.dataset.name);
        });
    });

    if (!orderedNames.length) {
        frappe.show_alert({ message: __("Нет данных для сохранения."), indicator: "orange" });
        return;
    }

    // ── UI: disable button, show spinner ─────────────────────────────────
    dlg.disable_primary_action();
    const origLabel = __("💾 Сохранить порядок");
    dlg.set_primary_action(__("⏳ Сохранение…"), () => {});

    frappe.call({
        method: "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.save_category_order",
        args:   { ordered_names: JSON.stringify(orderedNames) },

        callback: function (r) {
            if (r.message && r.message.status === "ok") {

                // ── Success ───────────────────────────────────────────────
                frappe.show_alert({
                    message  : __(
                        "Порядок сохранён ({0} категорий). Отчёт обновляется…",
                        [r.message.count]
                    ),
                    indicator: "green",
                });

                dlg.hide();

                // Small delay so user sees the success alert before reload
                setTimeout(() => { report.refresh(); }, 400);

            } else {
                // ── Unexpected empty response ─────────────────────────────
                frappe.show_alert({
                    message  : __("Неожиданный ответ сервера. Попробуйте снова."),
                    indicator: "orange",
                });
                _restore_save_button(dlg, origLabel);
            }
        },

        error: function (err) {
            // ── Server / permission error ─────────────────────────────────
            console.error("save_category_order error:", err);

            const msg = (err && err.message)
                ? err.message
                : __("Серверная ошибка при сохранении порядка.");

            frappe.show_alert({ message: msg, indicator: "red" });
            _restore_save_button(dlg, origLabel);
        },
    });
}


// =============================================================================
// UTILITY HELPERS
// =============================================================================

/**
 * Re-apply alternating row background after a drag-and-drop reorder
 * so the zebra striping stays correct.
 */
function _restripe(ul) {
    const items = ul.querySelectorAll("li[data-name]");
    items.forEach((li, idx) => {
        li.style.background = idx % 2 === 0 ? "#FFFFFF" : "#FAFAFA";
    });
}

/**
 * Re-enable the save button and restore its label after an error.
 */
function _restore_save_button(dlg, label) {
    dlg.enable_primary_action();
    dlg.set_primary_action(label, () => _save_order(dlg));
}

/**
 * Convert an activity name to a safe HTML id slug.
 * "Операционная деятельность" → "operacionnaya-deyatelnost"
 * We just use a simple char-strip approach to avoid transliteration complexity.
 */
function _slugify(str) {
    return str
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9\-а-яё]/gi, "")
        .substring(0, 40);
}
