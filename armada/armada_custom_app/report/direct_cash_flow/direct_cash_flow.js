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
                        frappe.show_alert({
                            message: __("Ошибка: пустой ответ от сервера."),
                            indicator: "red",
                        });
                        return;
                    }
                    try {
                        const byteChars = atob(r.message);
                        const bytes     = new Uint8Array(byteChars.length);
                        for (let i = 0; i < byteChars.length; i++) {
                            bytes[i] = byteChars.charCodeAt(i);
                        }
                        const blob = new Blob([bytes], { type: "application/pdf" });
                        const url  = URL.createObjectURL(blob);

                        const company  = (filters.company || "report").replace(/\s+/g, "_");
                        const filename = `DDS_${company}_${filters.from_date}_${filters.to_date}.pdf`;

                        const a = document.createElement("a");
                        a.href     = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);

                        setTimeout(() => URL.revokeObjectURL(url), 5000);

                        frappe.show_alert({ message: __("PDF успешно скачан."), indicator: "green" });
                    } catch (err) {
                        console.error("PDF decode error:", err);
                        frappe.show_alert({
                            message: __("Ошибка при обработке PDF."),
                            indicator: "red",
                        });
                    }
                },

                error: function (err) {
                    console.error("PDF export server error:", err);
                    frappe.show_alert({
                        message: __("Серверная ошибка при генерации PDF."),
                        indicator: "red",
                    });
                },
            });
        });
    },

    // -------------------------------------------------------------------------
    // CELL FORMATTER
    // BUG FIX: original code had broken `<s  pan` tag — corrected to `<span>`
    // -------------------------------------------------------------------------
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // Activity header rows — bold red
        if (data.is_activity_header) {
            value = `<span style="font-weight:700; color:#c0392b;">${value || ""}</span>`;
        }

        // Balance rows — bold dark
        if (data.is_balance_row) {
            value = `<span style="font-weight:700;">${value || ""}</span>`;
        }

        // Subtotal rows — semi-bold
        if (data.is_subtotal) {
            value = `<span style="font-weight:600;">${value || ""}</span>`;
        }

        // Negative numbers in data rows → red parentheses
        // BUG FIX: was `<s  pan` (broken tag) → now correct `<span>`
        if (
            data.row_type === "data" &&
            column.fieldtype === "Currency" &&
            typeof value === "string"
        ) {
            let raw = null;
            if (data[column.fieldname] !== undefined) {
                raw = data[column.fieldname];
            }
            if (raw !== null && parseFloat(raw) < 0) {
                const absVal = Math.abs(parseFloat(raw)).toLocaleString("ru-RU", {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 2,
                });
                value = `<span style="color:#c0392b;">(${absVal})</span>`;
            }
        }

        return value;
    },
};
