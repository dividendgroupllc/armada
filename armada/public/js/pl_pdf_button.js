// pl_pdf_button.js
(function () {
    "use strict";

    var REPORT_NAME = "Profit and Loss Statement";

    function _round_summary() {
        $(".report-summary .summary-value").each(function () {
            var $el = $(this);
            var text = $el.text().trim();

            var match = text.match(/^([^\d\-]*)([\d\s\.\,\-]+)$/);
            if (!match) return;

            var prefix = match[1];
            var numStr = match[2].trim();

            var cleaned = numStr
                .replace(/\s/g, "")
                .replace(/,/g, ".");

            var num = parseFloat(cleaned);
            if (isNaN(num)) return;

            var rounded = Math.round(num);
            var formatted = rounded
                .toLocaleString("fr-FR")
                .replace(/,/g, ",");

            $el.text(prefix + formatted);
        });
    }

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
        if (report.page.inner_toolbar.find(".btn-pl-custom-pdf").length) return;

        report.page.add_inner_button(
            __("Custom PDF"),
            _on_click
        ).addClass("btn-pl-custom-pdf btn-primary-dark");
    }

    $(document).ready(function () {
        var waitForReport = setInterval(function () {
            if (frappe.query_reports && frappe.query_reports[REPORT_NAME]) {
                clearInterval(waitForReport);

                var orig = frappe.query_reports[REPORT_NAME];
                var originalOnload = orig.onload;
                var originalRefresh = orig.refresh;

                orig.formatter = function (value, row, column, data, df) {
                    return frappe.armada.currency_formatter(
                        value, row, column, data, df, 0
                    );
                };

                orig.onload = function (report) {
                    if (originalOnload) originalOnload.call(this, report);
                    setTimeout(function () {
                        _inject_button(report);
                        _round_summary();
                    }, 300);
                };

                orig.refresh = function (report) {
                    if (originalRefresh) originalRefresh.call(this, report);
                    setTimeout(function () {
                        _inject_button(report);
                        _round_summary();
                    }, 500);
                };

                orig.after_datatable_render = function () {
                    setTimeout(_round_summary, 200);
                };
            }
        }, 100);
    });
})();
