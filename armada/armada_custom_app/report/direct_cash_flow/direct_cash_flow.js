frappe.query_reports["Direct Cash Flow"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.year_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.nowdate(),
        },
        {
            fieldname: "display_type",
            label: __("Display Type"),
            fieldtype: "Select",
            options: "Monthly\nQuarterly\nWeekly\nDaily",
            default: "Monthly",
            reqd: 1,
        },
        {
            fieldname: "party_type",
            label: __("Party Type"),
            fieldtype: "Link",
            options: "Party Type",
            reqd: 0,
        },
    ],

    // -------------------------------------------------------------------------
    // PDF EXPORT BUTTON
    // -------------------------------------------------------------------------
    onload: function (report) {
        report.page.add_inner_button(__("Экспорт PDF"), function () {
            const filters = report.get_values();
            if (!filters) {
                frappe.msgprint(__("Пожалуйста, заполните фильтры перед экспортом."));
                return;
            }

            frappe.show_alert({ message: __("Генерация PDF…"), indicator: "orange" });

            frappe.call({
                method: "armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.export_pdf",
                args: { filters: JSON.stringify(filters) },
                freeze: true,
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
                        const filename = `DDS_${company}_${filters.from_date}_${filters.to_date}.pdf`;

                        const a = document.createElement("a");
                        a.href = url; a.download = filename;
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
        const isInflow  = data.is_inflow === 1;   // set by Python on every data row

        // ── Activity header rows ──
        if (data.is_activity_header) {
            value = `<span style="font-weight:700; color:#c0392b;">${value || ""}</span>`;
        }

        // ── Balance rows (opening / closing) ──
        if (data.is_balance_row) {
            value = `<span style="font-weight:700;">${value || ""}</span>`;
        }

        // ── Subtotal rows ──
        if (data.is_subtotal) {
            value = `<span style="font-weight:600;">${value || ""}</span>`;
        }

        if (data.row_type === "data") {

            // ── Label column: prefix + colour by inflow/outflow ──
            if (fieldname === "label") {
                const lbl    = (data.label || "").trim();
                const prefix = isInflow ? "+" : "-";
                const color  = isInflow ? "#27AE60" : "#C0392B";
                value = `<span style="color:${color};font-weight:700;">${prefix} ${frappe.utils.escape_html(lbl)}</span>`;
            }

            // ── Numeric columns: rounded display, colour by inflow/outflow ──
            if (column.fieldtype === "Currency" && raw !== null) {
                const v = parseFloat(raw);
                if (!isNaN(v)) {
                    const absRounded = Math.round(Math.abs(v));
                    const fmt = absRounded.toLocaleString("ru-RU", {
                        minimumFractionDigits: 0,
                        maximumFractionDigits: 0,
                    });
                    const color = isInflow ? "#27AE60" : "#C0392B";

                    if (v === 0) {
                        value = `<span style="color:#1C2833;font-weight:700;">0</span>`;
                    } else if (v < 0) {
                        // outflow: red parentheses
                        value = `<span style="color:#C0392B;font-weight:700;">(${fmt})</span>`;
                    } else {
                        // inflow: green
                        value = `<span style="color:#27AE60;font-weight:700;">${fmt}</span>`;
                    }
                }
            }
        }

        return value;
    },
};
