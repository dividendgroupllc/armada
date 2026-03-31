// /home/user/frappe-bench/apps/armada/armada/public/js/balance_sheet_pdf.js
(function () {
    "use strict";

    const REPORT_NAME = "Balance Sheet";

    function _is_bs_route() {
        try {
            var r = frappe.get_route();
            if (!r || !r.length) return false;
            return r[0] === "query-report" && r[1] === REPORT_NAME;
        } catch (e) {
            return false;
        }
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
            message: "Balance Sheet PDF tayyorlanmoqda...",
            indicator: "blue",
        });

        frappe.call({
            method: "armada.armada_custom_app.api.balance_pdf_api.generate_balance_pdf",
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

    function _add_btn() {
        if ($(".btn-bs-custom-pdf").length) return;

        // 1-usul: frappe.query_report.page API orqali (ishonchli)
        if (
            frappe.query_report &&
            frappe.query_report.page &&
            frappe.query_report.report_name === REPORT_NAME
        ) {
            frappe.query_report.page.add_inner_button(
                __("Custom PDF"),
                _on_click
            ).addClass("btn-bs-custom-pdf btn-primary-dark");
            return;
        }

        // 2-usul: fallback — DOM ga to'g'ridan-to'g'ri qo'shish
        var $actions = $(".page-head .standard-actions");
        if (!$actions.length) return;

        var $btn = $(
            '<button class="btn btn-primary btn-sm btn-bs-custom-pdf"' +
                ' style="margin-right:6px;">Custom PDF</button>'
        ).on("click", _on_click);

        // primary-action buttondan oldin joylashtirish
        var $primary = $actions.find(".primary-action");
        if ($primary.length) {
            $primary.before($btn);
        } else {
            $actions.prepend($btn);
        }
    }

    function _poll_and_inject() {
        if (!_is_bs_route()) return;

        var attempts = 0;
        var timer = setInterval(function () {
            attempts++;

            if (!_is_bs_route() || attempts > 80) {
                clearInterval(timer);
                return;
            }

            // frappe.query_report to'liq tayyor bo'lishini kutish
            if (
                frappe.query_report &&
                frappe.query_report.report_name === REPORT_NAME &&
                frappe.query_report.page &&
                $(".page-head .standard-actions").length &&
                !$(".btn-bs-custom-pdf").length
            ) {
                clearInterval(timer);
                // report onload tugashini kutish uchun kichik kechikish
                setTimeout(_add_btn, 500);
            }
        }, 250);
    }

    $(document).on("page-change", function () {
        $(".btn-bs-custom-pdf").remove();
        if (_is_bs_route()) {
            setTimeout(_poll_and_inject, 200);
        }
    });

    $(document).ready(function () {
        if (_is_bs_route()) {
            setTimeout(_poll_and_inject, 800);
        }
    });
})();
