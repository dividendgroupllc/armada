// Copyright (c) 2026, Armada and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sotuv Hisoboti"] = {
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
			fieldname: "customer",
			label: __("Мижоз"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "item_code",
			label: __("Товар"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Товар гуруҳи"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "warehouse",
			label: __("Омбор"),
			fieldtype: "Link",
			options: "Warehouse",
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

	formatter: function (value, row, column, data, default_formatter) {
		// Jami qatorida narxlar yig'indisi ma'nosiz
		if (column.fieldname === "rate" && (!data || !data.invoice)) {
			return "";
		}
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "qty" && data && data.qty < 0) {
			value = `<span style="color: #c62828;">${value}</span>`;
		}
		if (column.fieldname === "komment" && data && data.invoice && !data.komment) {
			value = `<span style="color: #bbb; font-style: italic;">— изоҳ йўқ —</span>`;
		}
		return value;
	},
};
