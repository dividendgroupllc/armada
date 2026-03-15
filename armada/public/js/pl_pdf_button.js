// ERPNext 15 bug fix — bo'sh filter xatosini suppress qil
const _orig_msgprint = frappe.msgprint.bind(frappe);
frappe.msgprint = function(msg, ...args) {
    if (typeof msg === "string" &&
        msg.includes("From Date and To Date")) return;
    if (msg && msg.message &&
        msg.message.includes("From Date and To Date")) return;
    return _orig_msgprint(msg, ...args);
};
$(document).on("page-change", function() {
    var route = frappe.get_route();
    if (route[0] === "query-report" && route[1] === "Profit and Loss Statement") {
        if ($(".btn-pl-custom-pdf").length) return;
        setTimeout(function() {
            if (frappe.query_report && frappe.query_report.page) {
                frappe.query_report.page
                    .add_inner_button(__("Custom PDF"), function() {
                        var filters = frappe.query_report.get_filter_values();
                        frappe.show_alert({ message: "PDF tayyorlanmoqda...", indicator: "blue" });
                        frappe.call({
                            method: "armada.armada_custom_app.api.pl_pdf_api.generate_pl_pdf",
                            args: { filters: JSON.stringify(filters) },
                            callback: function(r) {
                                if (r.message && r.message.file_url) {
                                    window.open(r.message.file_url);
                                    frappe.show_alert({ message: "PDF tayyor", indicator: "green" });
                                }
                            }
                        });
                    }).addClass("btn-pl-custom-pdf");
            }
        }, 500);
    }
});
