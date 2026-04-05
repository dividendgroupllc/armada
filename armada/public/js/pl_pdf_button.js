// pl_pdf_button.js
// Survives Frappe SPA navigation — patches are re-applied automatically
// when Frappe's eval() recreates the report config object.
(function () {
    "use strict";

    var REPORT_NAME = "Profit and Loss Statement";
    var BTN_CLASS = "btn-pl-custom-pdf";

    function _on_click() {
        if (!frappe.query_report) return;

        var filters = frappe.query_report.get_filter_values();
        var mode = filters.filter_based_on || "Fiscal Year";

        if (mode === "Date Range") {
            if (!filters.period_start_date || !filters.period_end_date) {
                frappe.show_alert({
                    message: "Avval 'From Date' va 'To Date' ni tanlang",
                    indicator: "orange",
                });
                return;
            }
        } else {
            if (!filters.from_fiscal_year || !filters.to_fiscal_year) {
                frappe.show_alert({
                    message: "Avval 'Start Year' va 'End Year' ni tanlang",
                    indicator: "orange",
                });
                return;
            }
        }

        frappe.show_alert({
            message: "PDF tayyorlanmoqda...",
            indicator: "blue",
        });

        frappe.call({
            method: "armada.armada_custom_app.api.pl_pdf_api.generate_pl_pdf",
            args: { filters: JSON.stringify(filters) },
            freeze: true,
            freeze_message: "PDF yaratilmoqda...",
            callback: function (r) {
                if (r.message && r.message.file_url) {
                    window.open(r.message.file_url);
                    frappe.show_alert({
                        message: "PDF tayyor!",
                        indicator: "green",
                    });
                } else {
                    frappe.show_alert({
                        message: "Fayl URL qaytmadi",
                        indicator: "red",
                    });
                }
            },
            error: function () {
                frappe.show_alert({
                    message: "Server xatoligi",
                    indicator: "red",
                });
            },
        });
    }

    function _inject_button(report) {
        if (!report || !report.page) return;
        if (report.page.inner_toolbar.find("." + BTN_CLASS).length) return;

        report.page
            .add_inner_button(__("Custom PDF"), _on_click)
            .addClass(BTN_CLASS + " btn-primary-dark");
    }

    // This function is called by frappe.armada.patch_report EVERY TIME
    // Frappe recreates the report config (on each SPA navigation).
    frappe.armada.patch_report(REPORT_NAME, function (reportConfig) {
        var _origOnload = reportConfig.onload;
        var _origRefresh = reportConfig.refresh;
        var _origAfterRender = reportConfig.after_datatable_render;

        reportConfig.formatter = function (value, row, column, data, df) {
            return frappe.armada.currency_formatter(value, row, column, data, df, 0);
        };

        reportConfig.onload = function (report) {
            if (_origOnload) _origOnload.call(this, report);
            setTimeout(function () {
                _inject_button(report);
                frappe.armada.round_summary();
            }, 300);
        };

        reportConfig.refresh = function (report) {
            if (_origRefresh) _origRefresh.call(this, report);
            setTimeout(function () {
                _inject_button(report);
                frappe.armada.round_summary();
            }, 500);
        };

        reportConfig.after_datatable_render = function (datatable) {
            if (_origAfterRender) _origAfterRender.call(this, datatable);
            setTimeout(frappe.armada.round_summary, 200);
        };
    });

})();
