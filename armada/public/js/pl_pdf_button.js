(function () {
    "use strict";

    // 1. CSS inject — bir marta, sahifa load bo'lganda
    if (!document.getElementById("pl-pdf-style")) {
        var style = document.createElement("style");
        style.id = "pl-pdf-style";
        style.innerHTML = [
            '[data-page-route="query-report/Profit%20and%20Loss%20Statement"] .custom-actions,',
            '.query-report-wrapper .custom-actions {',
            '    display: flex !important;',
            '    visibility: visible !important;',
            '}'
        ].join("\n");
        document.head.appendChild(style);
    }

    // 2. msgprint fix
    const _orig = frappe.msgprint.bind(frappe);
    frappe.msgprint = function (msg, ...args) {
        if (typeof msg === "string" && msg.includes("From Date and To Date")) return;
        if (msg && msg.message && msg.message.includes("From Date and To Date")) return;
        return _orig(msg, ...args);
    };

    // 3. Button logic
    function _add_pl_btn() {
        var route = frappe.get_route();
        if (route[0] !== "query-report" || route[1] !== "Profit and Loss Statement") return;
        if ($(".btn-pl-custom-pdf").length) return;
        if (!frappe.query_report || !frappe.query_report.page) return;

        frappe.query_report.page
            .add_inner_button(__("Custom PDF"), function () {
                var filters = frappe.query_report.get_filter_values();
                frappe.show_alert({ message: "PDF tayyorlanmoqda...", indicator: "blue" });
                frappe.call({
                    method: "armada.armada_custom_app.api.pl_pdf_api.generate_pl_pdf",
                    args: { filters: JSON.stringify(filters) },
                    callback: function (r) {
                        if (r.message && r.message.file_url) {
                            window.open(r.message.file_url);
                            frappe.show_alert({ message: "PDF tayyor", indicator: "green" });
                        }
                    }
                });
            }).addClass("btn-pl-custom-pdf");

        $(".custom-actions")
            .removeClass("hidden-xs hidden-md hidden-sm hidden")
            .css({ "display": "flex", "visibility": "visible" });
    }

    // 4. URL orqali to'g'ri kirganda
    frappe.ready(function () {
        setTimeout(_add_pl_btn, 1000);
    });

    // 5. App ichida navigate qilinganda
    $(document).on("page-change", function () {
        $(".btn-pl-custom-pdf").remove();
        setTimeout(_add_pl_btn, 500);
    });

})();
