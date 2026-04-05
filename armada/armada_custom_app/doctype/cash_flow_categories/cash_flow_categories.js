// Copyright (c) 2026, Sardorbek and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cash Flow Categories", {
	refresh(frm) {
		load_used_accounts(frm);

		frm.fields_dict.direct_cash_flow.grid.get_field("direct_expence_account").get_query = function (doc, cdt, cdn) {
			const used = frm._used_accounts || [];
			const current_accounts = (frm.doc.direct_cash_flow || [])
				.filter((row) => row.name !== cdn && row.direct_expence_account)
				.map((row) => row.direct_expence_account);

			const exclude = [...new Set([...used, ...current_accounts])];

			const filters = {};
			if (exclude.length > 0) {
				filters.name = ["not in", exclude];
			}
			return { filters: filters };
		};
	},

	after_save(frm) {
		load_used_accounts(frm);
	},
});

function load_used_accounts(frm) {
	frappe.call({
		method: "armada.armada_custom_app.doctype.cash_flow_categories.cash_flow_categories.get_used_accounts",
		args: { exclude_parent: frm.doc.name || "" },
		callback: function (r) {
			frm._used_accounts = r.message || [];
		},
	});
}
