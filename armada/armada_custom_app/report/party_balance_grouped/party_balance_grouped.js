// Party Balance Grouped — Full Balance Sheet Replacement
// ERPNext v15 | Armada Custom App
//
// Tree expand/collapse: Frappe handles it natively via `indent` + `is_group`
// fields returned from Python. No extra JS needed for tree logic.

frappe.query_reports["Party Balance Grouped"] = {

	"onload": function (report) {
		// Default fiscal year va datalarni avtomatik set qilish
		let fiscal_year = frappe.defaults.get_user_default("fiscal_year");
		if (!fiscal_year) return;

		frappe.db
			.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
			.then((r) => {
				if (r && r.message) {
					frappe.query_report.set_filter_value({
						from_fiscal_year:  fiscal_year,
						to_fiscal_year:    fiscal_year,
						period_start_date: r.message.year_start_date,
						period_end_date:   r.message.year_end_date,
						filter_based_on:   "Fiscal Year",
					});
				}
			});
	},

	// ── Tree configuration ─────────────────────────────────────────────────
	// Frappe query report tree: rows with `indent` field are shown as tree.
	// Rows with `is_group=true` get expand/collapse toggle.
	"tree": true,
	"name_field": "account",
	"parent_field": "parent_account",
	"initial_depth": 3,   // 0=root 1=section 2=account_group 3=account (party accounts collapsed)

	// ── Filters ────────────────────────────────────────────────────────────
	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "filter_based_on",
			label: __("Filter Based On"),
			fieldtype: "Select",
			options: ["Fiscal Year", "Date Range"],
			default: "Fiscal Year",
			reqd: 1,
			on_change: function () {
				let v = frappe.query_report.get_filter_value("filter_based_on");
				if (v === "Fiscal Year") {
					frappe.query_report.toggle_filter_display("from_fiscal_year", false);
					frappe.query_report.toggle_filter_display("to_fiscal_year", false);
					frappe.query_report.toggle_filter_display("period_start_date", true);
					frappe.query_report.toggle_filter_display("period_end_date", true);
				} else {
					frappe.query_report.toggle_filter_display("from_fiscal_year", true);
					frappe.query_report.toggle_filter_display("to_fiscal_year", true);
					frappe.query_report.toggle_filter_display("period_start_date", false);
					frappe.query_report.toggle_filter_display("period_end_date", false);
				}
			},
		},
		{
			fieldname: "period_start_date",
			label: __("Start Date"),
			fieldtype: "Date",
			hidden: 1,
		},
		{
			fieldname: "period_end_date",
			label: __("End Date"),
			fieldtype: "Date",
			hidden: 1,
		},
		{
			fieldname: "from_fiscal_year",
			label: __("Start Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			on_change: function () {
				let fy = frappe.query_report.get_filter_value("from_fiscal_year");
				if (!fy) return;
				frappe.db.get_value("Fiscal Year", fy, "year_start_date").then((r) => {
					if (r && r.message) {
						frappe.query_report.set_filter_value({
							period_start_date: r.message.year_start_date,
						});
					}
				});
			},
		},
		{
			fieldname: "to_fiscal_year",
			label: __("End Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			on_change: function () {
				let fy = frappe.query_report.get_filter_value("to_fiscal_year");
				if (!fy) return;
				frappe.db.get_value("Fiscal Year", fy, "year_end_date").then((r) => {
					if (r && r.message) {
						frappe.query_report.set_filter_value({
							period_end_date: r.message.year_end_date,
						});
					}
				});
			},
		},
		{
			fieldname: "periodicity",
			label: __("Periodicity"),
			fieldtype: "Select",
			options: [
				{ value: "Monthly",     label: __("Monthly") },
				{ value: "Quarterly",   label: __("Quarterly") },
				{ value: "Half-Yearly", label: __("Half-Yearly") },
				{ value: "Yearly",      label: __("Yearly") },
			],
			default: "Yearly",
			reqd: 1,
		},
		{
			fieldname: "accumulated_values",
			label: __("Accumulated Values"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "MultiSelectList",
			options: "Cost Center",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "include_default_book_entries",
			label: __("Include Default Book Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_zero_balance",
			label: __("Show Zero Balance Parties"),
			fieldtype: "Check",
			default: 1,
		},
	],

	// ── Formatter ──────────────────────────────────────────────────────────
	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		let indent  = data.indent || 0;
		let is_grp  = data.is_group;
		let acc     = cstr(data.account || "");

		// Party group row (indent >= 4, is_group=true) — bold teal
		let is_party_group = is_grp && acc.includes("::");
		// Individual party row (indent >= 5, is_group=false, has "::")
		let is_party_leaf  = !is_grp && acc.includes("::");

		if (column.fieldname === "account") {
			// Show clean label — strip the namespaced key prefix
			let parts = acc.split("::");
			let label = parts[parts.length - 1] || value;

			if (is_party_group) {
				return `<span style="
					font-weight:600;
					color:var(--text-on-light-green, #1a7f5e);
					padding-left:${indent * 8}px;
				">📂 ${frappe.utils.escape_html(label)}</span>`;
			}
			if (is_party_leaf) {
				return `<span style="
					color:var(--text-muted);
					padding-left:${indent * 8}px;
				">└ ${frappe.utils.escape_html(label)}</span>`;
			}
		}

		// Currency: red if negative
		if (column.fieldtype === "Currency" && flt(value) < 0) {
			let formatted = default_formatter(value, row, column, data);
			return `<span style="color:var(--red-500,#e53e3e);">${formatted}</span>`;
		}

		// Root section rows (indent=0) — large bold
		if (indent === 0 && is_grp) {
			let formatted = default_formatter(value, row, column, data);
			return `<strong style="font-size:13px;">${formatted}</strong>`;
		}

		return default_formatter(value, row, column, data);
	},
};
