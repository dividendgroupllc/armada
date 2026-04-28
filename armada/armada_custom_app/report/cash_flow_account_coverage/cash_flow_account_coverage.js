/**
 * Cash Flow Account Coverage — Query Report JS
 * App    : armada / armada_custom_app
 * Frappe : v15
 *
 * FIX v2: Tugmalar formatter() ichida to'g'ridan HTML+onclick orqali render.
 *         after_datatable_render ISHLATILMAYDI — Frappe v15 virtual scroll bilan
 *         DOM injection ishonchsiz va ko'rinmaydi.
 *         onclick → window.cfac_* global functions → report instance orqali dialog.
 */

// =============================================================================
// GLOBAL STATE
// =============================================================================
window._cfac_report     = null;   // active report instance (onclick uchun)
window._cfac_categories = null;   // categories cache (har refresh da reset)

// =============================================================================
// GLOBAL ACTION HANDLERS
// HTML da: onclick="window.cfac_assign('AccountName')"
//          onclick="window.cfac_remove('ItemName','AccName','CatName')"
// =============================================================================

window.cfac_assign = function(accountDocName) {
    const report = window._cfac_report;
    if (!report) return;

    if (window._cfac_categories) {
        _render_assign_dialog(accountDocName, window._cfac_categories, report);
        return;
    }

    frappe.call({
        method: "armada.armada_custom_app.report.cash_flow_account_coverage.cash_flow_account_coverage.get_categories_for_assign",
        callback: function(r) {
            if (!r.message) {
                frappe.show_alert({ message: __("Не удалось загрузить категории."), indicator: "red" });
                return;
            }
            window._cfac_categories = r.message;
            _render_assign_dialog(accountDocName, r.message, report);
        },
        error: function() {
            frappe.show_alert({ message: __("Серверная ошибка."), indicator: "red" });
        },
    });
};


window.cfac_remove = function(categoryItemName, accountDocName, categoryName) {
    const report = window._cfac_report;
    if (!report) return;

    frappe.confirm(
        __(
            "Удалить привязку счёта <b>{0}</b> из категории <b>{1}</b>?",
            [frappe.utils.escape_html(accountDocName), frappe.utils.escape_html(categoryName)]
        ),
        function() {
            frappe.call({
                method: "armada.armada_custom_app.report.cash_flow_account_coverage.cash_flow_account_coverage.remove_account_from_category",
                args: { category_item_name: categoryItemName },
                callback: function(r) {
                    if (r.message && r.message.status === "ok") {
                        window._cfac_categories = null;
                        frappe.show_alert({ message: r.message.message, indicator: "green" });
                        setTimeout(() => { report.refresh(); }, 300);
                    } else {
                        frappe.show_alert({ message: __("Ошибка удаления."), indicator: "red" });
                    }
                },
                error: function(err) {
                    console.error("remove error:", err);
                    frappe.show_alert({ message: __("Серверная ошибка."), indicator: "red" });
                },
            });
        }
    );
};


// =============================================================================
// REPORT DEFINITION
// =============================================================================

frappe.query_reports["Cash Flow Account Coverage"] = {

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
            fieldname: "account_type",
            label:     __("Account Type"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                const types = [
                    "Cash", "Bank", "Receivable", "Payable",
                    "Tax", "Expense Account", "Income Account",
                    "Fixed Asset", "Accumulated Depreciation",
                    "Cost of Goods Sold", "Stock",
                    "Capital Work in Progress", "Equity",
                    "Liability", "Temporary",
                ];
                return types
                    .filter(t => !txt || t.toLowerCase().includes(txt.toLowerCase()))
                    .map(t => ({ value: t, description: t }));
            },
        },
        {
            fieldname: "show_unmapped_only",
            label:     __("Show Unmapped Only"),
            fieldtype: "Check",
            default:   0,
        },
    ],

    // -------------------------------------------------------------------------
    // ON LOAD
    // -------------------------------------------------------------------------
    onload: function(report) {
        window._cfac_report     = report;
        window._cfac_categories = null;
        _inject_styles();
    },

    // -------------------------------------------------------------------------
    // FORMATTER — tugmalar shu yerda, DOM injection yo'q
    // -------------------------------------------------------------------------
    formatter: function(value, row, column, data, default_formatter) {
        if (!data) return default_formatter(value, row, column, data);

        const fn = column.fieldname;
        const rt = data.row_type;

        // ── Section headers ───────────────────────────────────────────────
        if (rt === "section_header") {
            if (fn === "account_name") {
                const COLOR_MAP = {
                    "Операционная деятельность":  { bg: "#E67E22", icon: "💼" },
                    "Инвестиционная деятельность": { bg: "#2980B9", icon: "📈" },
                    "Финансовая деятельность":     { bg: "#27AE60", icon: "🏦" },
                };
                const meta = COLOR_MAP[value] || { bg: "#E74C3C", icon: "✗" };
                return `<span style="display:inline-block;background:${meta.bg};color:#fff;
                    font-weight:700;font-size:12px;padding:4px 12px;border-radius:3px;"
                >${meta.icon} ${frappe.utils.escape_html(value || "")}</span>`;
            }
            return "";
        }

        // ── Sub-headers ───────────────────────────────────────────────────
        if (rt === "sub_header") {
            if (fn === "account_name") {
                const color = (data.sub_type === "mapped") ? "#27AE60" : "#C0392B";
                return `<span style="color:${color};font-weight:700;font-size:11px;
                    font-style:italic;padding-left:8px;"
                >${frappe.utils.escape_html(value || "")}</span>`;
            }
            return "";
        }

        // ── Empty ─────────────────────────────────────────────────────────
        if (rt === "empty") {
            if (fn === "account_name") {
                return `<span style="color:#BDC3C7;font-style:italic;padding-left:16px;">
                    ${frappe.utils.escape_html(value || "")}</span>`;
            }
            return "";
        }

        // ── Spacer ────────────────────────────────────────────────────────
        if (rt === "spacer") return "";

        // ── Summary ───────────────────────────────────────────────────────
        if (rt === "summary") {
            if (fn === "account_name") {
                return `<span style="font-weight:700;font-size:12px;color:#2C3E50;
                    border-top:2px solid #D5D8DC;display:block;padding-top:4px;"
                >${frappe.utils.escape_html(value || "")}</span>`;
            }
            return "";
        }

        // ── Data rows ─────────────────────────────────────────────────────
        if (rt !== "data") return default_formatter(value, row, column, data);

        const isGrp    = data._is_group;
        const isMapped = data.status === "mapped";
        const canAssign = data.can_assign === "1";

        // ── Account name + action button ──────────────────────────────────
        if (fn === "account_name") {
            const color  = isGrp ? "#7F8C8D" : isMapped ? "#2C3E50" : "#C0392B";
            const weight = isGrp ? "600" : "500";
            const prefix = isGrp ? "📁 " : "&nbsp;&nbsp;&nbsp;&nbsp;";

            const label = `<span style="color:${color};font-weight:${weight};font-size:12px;">
                ${prefix}${frappe.utils.escape_html(value || "")}
            </span>`;

            let btn = "";

            if (canAssign && !isMapped) {
                // Escape single quotes for safe inline onclick
                const acc = (data.account_doc_name || "").replace(/\\/g,"\\\\").replace(/'/g,"\\'");
                btn = `<button
                    onclick="window.cfac_assign('${acc}')"
                    style="background:#2471A3;color:#fff;border:none;border-radius:4px;
                           padding:2px 10px;font-size:10px;font-weight:700;cursor:pointer;
                           margin-left:8px;vertical-align:middle;"
                >+ ${__("Назначить")}</button>`;

            } else if (canAssign && isMapped && data.category_item_name) {
                const item = (data.category_item_name || "").replace(/\\/g,"\\\\").replace(/'/g,"\\'");
                const acc  = (data.account_doc_name   || "").replace(/\\/g,"\\\\").replace(/'/g,"\\'");
                const cat  = (data.category_name      || "").replace(/\\/g,"\\\\").replace(/'/g,"\\'");
                btn = `<button
                    onclick="window.cfac_remove('${item}','${acc}','${cat}')"
                    style="background:transparent;color:#C0392B;border:1px solid #F1948A;
                           border-radius:4px;padding:2px 8px;font-size:10px;font-weight:700;
                           cursor:pointer;margin-left:8px;vertical-align:middle;"
                >✕ ${__("Отвязать")}</button>`;
            }

            return label + btn;
        }

        // ── Status badge ──────────────────────────────────────────────────
        if (fn === "status") {
            if (value === "mapped") {
                return `<span style="background:#D5F5E3;color:#1E8449;font-weight:700;
                    font-size:10px;padding:2px 8px;border-radius:10px;
                    border:1px solid #A9DFBF;">✓ Назначен</span>`;
            }
            if (value === "unmapped") {
                return `<span style="background:#FDEDEC;color:#C0392B;font-weight:700;
                    font-size:10px;padding:2px 8px;border-radius:10px;
                    border:1px solid #F1948A;">✗ Не назначен</span>`;
            }
            return default_formatter(value, row, column, data);
        }

        // ── Direction badge ───────────────────────────────────────────────
        if (fn === "direction" && value) {
            const isIn  = value === "Приход";
            const bg    = isIn ? "#EBF5FB" : "#FDEDEC";
            const color = isIn ? "#1A5276" : "#922B21";
            const arrow = isIn ? "↑" : "↓";
            return `<span style="background:${bg};color:${color};font-weight:600;
                font-size:10px;padding:2px 7px;border-radius:8px;"
            >${arrow} ${frappe.utils.escape_html(value)}</span>`;
        }

        // ── Is Group badge ────────────────────────────────────────────────
        if (fn === "is_group") {
            if (value === "Да") {
                return `<span style="color:#7F8C8D;font-size:10px;font-style:italic;">Да</span>`;
            }
            return `<span style="color:#BDC3C7;font-size:10px;">Нет</span>`;
        }

        // ── Category name ─────────────────────────────────────────────────
        if (fn === "category_name" && value) {
            return `<span style="color:#2471A3;font-weight:600;font-size:11px;">
                ${frappe.utils.escape_html(value)}</span>`;
        }

        return default_formatter(value, row, column, data);
    },
};


// =============================================================================
// ASSIGN DIALOG
// =============================================================================

function _render_assign_dialog(accountDocName, categories, report) {
    const dlg = new frappe.ui.Dialog({
        title: __("Назначить счёт в категорию"),
        size:  "small",
        fields: [
            {
                fieldname: "account_display",
                fieldtype: "Data",
                label:     __("Счёт"),
                read_only: 1,
                default:   accountDocName,
            },
            { fieldtype: "Section Break", label: __("Привязка") },
            {
                fieldname:   "category_name",
                fieldtype:   "Link",
                label:       __("Cash Flow Category"),
                options:     "Cash Flow Categories",
                reqd:        1,
                description: __("Выберите категорию из справочника"),
            },
            {
                fieldname:   "direction_override",
                fieldtype:   "Select",
                label:       __("Direction Override"),
                options:     "\n(blank)\nПриход (Inflow)\nРасход (Outflow)",
                default:     "",
                description: __("Оставьте пустым — используется тип категории"),
            },
            {
                fieldname:   "account_label",
                fieldtype:   "Data",
                label:       __("Account Label"),
                description: __("Необязательно: пользовательское имя в отчёте"),
            },
        ],
        primary_action_label: __("💾 Сохранить привязку"),
        primary_action: function(values) {
            if (!values.category_name) {
                frappe.show_alert({ message: __("Выберите категорию."), indicator: "orange" });
                return;
            }

            dlg.disable_primary_action();
            dlg.set_primary_action(__("⏳ Сохранение…"), () => {});

            frappe.call({
                method: "armada.armada_custom_app.report.cash_flow_account_coverage.cash_flow_account_coverage.assign_account_to_category",
                args: {
                    account_name:       accountDocName,
                    category_name:      values.category_name,
                    direction_override: values.direction_override || "",
                    account_label:      values.account_label      || "",
                },
                callback: function(r) {
                    if (!r.message) {
                        frappe.show_alert({ message: __("Неожиданный ответ."), indicator: "orange" });
                        dlg.enable_primary_action();
                        dlg.set_primary_action(__("💾 Сохранить привязку"), () => {});
                        return;
                    }
                    if (r.message.status === "duplicate") {
                        frappe.show_alert({ message: r.message.message, indicator: "orange" });
                        dlg.enable_primary_action();
                        dlg.set_primary_action(__("💾 Сохранить привязку"), () => {});
                        return;
                    }
                    if (r.message.status === "ok") {
                        window._cfac_categories = null;
                        frappe.show_alert({ message: r.message.message, indicator: "green" });
                        dlg.hide();
                        setTimeout(() => { report.refresh(); }, 300);
                    }
                },
                error: function(err) {
                    console.error("assign error:", err);
                    frappe.show_alert({
                        message: (err && err.message) || __("Серверная ошибка."),
                        indicator: "red",
                    });
                    dlg.enable_primary_action();
                    dlg.set_primary_action(__("💾 Сохранить привязку"), () => {});
                },
            });
        },
    });

    dlg.show();
}


// =============================================================================
// STYLES
// =============================================================================

function _inject_styles() {
    if (document.getElementById("cfac-styles")) return;
    const s = document.createElement("style");
    s.id = "cfac-styles";
    s.textContent = `
        button[onclick^="window.cfac_assign"]:hover { background:#1A5276 !important; }
        button[onclick^="window.cfac_remove"]:hover { background:#FDEDEC !important; }
    `;
    document.head.appendChild(s);
}
