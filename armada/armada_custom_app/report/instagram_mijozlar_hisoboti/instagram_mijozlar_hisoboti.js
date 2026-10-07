// Copyright (c) 2026, Armada and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Instagram Mijozlar Hisoboti"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Бошланғич сана"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.now_date(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Охирги сана"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "customer_group",
			label: __("Мижоз гуруҳи"),
			fieldtype: "Link",
			options: "Customer Group",
			default: "Инстаграм",
		},
		{
			fieldname: "customer",
			label: __("Мижоз"),
			fieldtype: "Link",
			options: "Customer",
			get_query: () => ({
				filters: { customer_group: frappe.query_report.get_filter_value("customer_group") },
			}),
		},
		{
			fieldname: "item_group",
			label: __("Товар гуруҳи"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "company",
			label: __("Компания"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "include_returns",
			label: __("Қайтаришлар билан"),
			fieldtype: "Check",
			default: 1,
		},
	],

	tree: true,
	name_field: "name",
	parent_field: "parent_row",
	initial_depth: 0,

	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "name" && data && data.label) {
			value = data.label;
		}
		// To'lov va qarz mijoz darajasida; invoys/tovar qatoriga bog'lab bo'lmaydi
		if (data && data.parent_row && ["paid", "debt", "paid_pct"].includes(column.fieldname)) {
			return "";
		}
		value = default_formatter(value, row, column, data);
		if (data && !data.parent_row && column.fieldname === "debt" && data.debt > 0) {
			value = `<span style="color: #c62828; font-weight: 600;">${value}</span>`;
		}
		if (data && !data.parent_row && column.fieldname === "paid" && data.paid > 0) {
			value = `<span style="color: #2e7d32; font-weight: 600;">${value}</span>`;
		}
		return value;
	},
};
