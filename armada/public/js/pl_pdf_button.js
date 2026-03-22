// /home/user/frappe-bench/apps/armada/armada/public/js/pl_pdf_button.js
(function () {
    "use strict";

    const REPORT_NAME = "Profit and Loss Statement";

    function _is_pl_route() {
        try {
            var r = frappe.get_route();
            if (!r || !r.length) return false;
            return r[0] === "query-report" && r[1] === REPORT_NAME;
        } catch(e) { return false; }
    }

    function _on_click() {
        if (!frappe.query_report) return;

        var filters = frappe.query_report.get_filter_values();
        var mode = filters.filter_based_on || "Fiscal Year";

        if (mode === "Date Range") {
            if (!filters.period_start_date || !filters.period_end_date) {
                frappe.show_alert({
                    message: "Avval 'From Date' va 'To Date' ni tanlang",
                    indicator: "orange"
                });
                return;
            }
        } else {
            if (!filters.from_fiscal_year || !filters.to_fiscal_year) {
                frappe.show_alert({
                    message: "Avval 'Start Year' va 'End Year' ni tanlang",
                    indicator: "orange"
                });
                return;
            }
        }

        frappe.show_alert({ message: "PDF tayyorlanmoqda...", indicator: "blue" });

        frappe.call({
            method: "armada.armada_custom_app.api.pl_pdf_api.generate_pl_pdf",
            args: { filters: JSON.stringify(filters) },
            callback: function (r) {
                if (r.message && r.message.file_url) {
                    window.open(r.message.file_url);
                    frappe.show_alert({ message: "PDF tayyor!", indicator: "green" });
                } else {
                    frappe.show_alert({ message: "Fayl URL qaytmadi", indicator: "red" });
                }
            },
            error: function () {
                frappe.show_alert({ message: "Server xatoligi", indicator: "red" });
            }
        });
    }

    function _add_btn() {
        if ($(".btn-pl-custom-pdf").length) return;

        // DOM dan aniqlangan: .standard-actions ichida .menu-btn-group DAN OLDIN
        var $menu = $(".standard-actions .menu-btn-group");
        if (!$menu.length) return;

        var $btn = $(
            '<button class="btn btn-primary btn-sm btn-pl-custom-pdf"' +
            ' style="margin-right:6px;">Custom PDF</button>'
        ).on("click", _on_click);

        // .menu-btn-group dan OLDIN — toolbar da ko'rinadi
        $menu.before($btn);
    }

    function _poll_and_inject() {
        if (!_is_pl_route()) return;

        var attempts = 0;
        var timer = setInterval(function () {
            attempts++;

            if (!_is_pl_route() || attempts > 40) {
                clearInterval(timer);
                return;
            }

            if ($(".standard-actions .menu-btn-group").length &&
                !$(".btn-pl-custom-pdf").length) {
                clearInterval(timer);
                _add_btn();
            }
        }, 250);
    }

    $(document).on("page-change", function () {
        $(".btn-pl-custom-pdf").remove();
        setTimeout(_poll_and_inject, 100);
    });

    $(document).ready(function () {
        setTimeout(_poll_and_inject, 500);
    });

})();
