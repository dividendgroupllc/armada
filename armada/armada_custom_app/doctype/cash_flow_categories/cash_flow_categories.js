// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cash Flow Categories", {
	refresh(frm) {
		frm.set_query("direct_expence_account", "direct_cash_flow", function() {
			return {
				query: "armada.armada_custom_app.doctype.cash_flow_categories_item.cash_flow_categories_item.get_indirect_accounts"
			};
		});
	},
});
