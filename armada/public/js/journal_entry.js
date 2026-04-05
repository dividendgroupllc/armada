frappe.ui.form.on("Journal Entry", {
    refresh: function(frm) {
        if (frm.doc.cheque_no && frm.doc.cheque_no.startsWith("KASSA-")) {
            let $field = frm.fields_dict.cheque_no;
            if ($field && $field.$wrapper) {
                $field.$wrapper.find(".like-disabled-input, .control-value").css({
                    "cursor": "pointer",
                    "color": "#2490EF",
                    "text-decoration": "underline"
                }).off("click.kassa_link").on("click.kassa_link", function() {
                    frappe.set_route("Form", "Kassa", frm.doc.cheque_no);
                });
            }
        }
    }
});
