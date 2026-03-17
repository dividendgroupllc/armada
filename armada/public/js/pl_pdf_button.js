(function () {
    "use strict";

    // CSS inject
    if (!document.getElementById("pl-pdf-style")) {
        var style = document.createElement("style");
        style.id = "pl-pdf-style";
        style.innerHTML =
            ".custom-actions { display: flex !important; visibility: visible !important; }";
        document.head.appendChild(style);
    }

    // msgprint fix
    const _orig = frappe.msgprint.bind(frappe);
    frappe.msgprint = function (msg, ...args) {
        if (typeof msg === "string" && msg.includes("From Date and To Date")) return;
        if (msg && msg.message && msg.message.includes("From Date and To Date")) return;
        return _orig(msg, ...args);
    };

    var _observer = null;

    function _add_pl_btn() {
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
    }

    function _start_observer() {
        if (_observer) { _observer.disconnect(); _observer = null; }

        var target = document.querySelector(".page-actions");
        if (!target) return;

        _observer = new MutationObserver(function () {
            var route = frappe.get_route();
            if (route[0] !== "query-report" ||
                route[1] !== "Profit and Loss Statement") return;
            // Frappe qayta render qildi — button yo'qolgan bo'lsa qayta qo'sh
            if (!$(".btn-pl-custom-pdf").length) {
                _add_pl_btn();
            }
        });

        _observer.observe(target, { childList: true, subtree: true });
    }

    function _init() {
        var route = frappe.get_route();
        if (route[0] !== "query-report" ||
            route[1] !== "Profit and Loss Statement") {
            if (_observer) { _observer.disconnect(); _observer = null; }
            return;
        }
        _add_pl_btn();
        _start_observer();
    }

    frappe.ready(function () { setTimeout(_init, 800); });

    $(document).on("page-change", function () {
        $(".btn-pl-custom-pdf").remove();
        setTimeout(_init, 500);
    });

})();
