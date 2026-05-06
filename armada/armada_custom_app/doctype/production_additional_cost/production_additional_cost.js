// Copyright (c) 2025, Sardorbek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Production Additional Cost', {
    refresh: function(frm) {
        // Set query for expense_account - only expense accounts
        frm.set_query("expense_account", function() {
            return {
                filters: {
                    "is_group": 0,
                    "root_type": "Expense"
                }
            };
        });
    }
});
