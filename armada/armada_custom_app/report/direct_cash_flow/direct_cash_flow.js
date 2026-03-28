frappe.query_reports["Direct Cash Flow"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.nowdate(),
		},
		{
			fieldname: "display_type",
			label: __("Display Type"),
			fieldtype: "Select",
			options: "Monthly\nQuarterly\nWeekly\nDaily",
			default: "Monthly",
			reqd: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "Party Type",
			reqd: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Activity header rows — bold + dark background text
		if (data.is_activity_header) {
			value = `<span style="font-weight:700; color:#c0392b;">${value || ""}</span>`;
		}

		// Balance rows — opening / closing
		if (data.is_balance_row) {
			value = `<span style="font-weight:700;">${value || ""}</span>`;
		}

		// Subtotal rows
		if (data.is_subtotal) {
			value = `<span style="font-weight:600;">${value || ""}</span>`;
		}

		// Negative numbers → red with parentheses
		if (
			data.row_type === "data" &&
			column.fieldtype === "Currency" &&
			typeof value === "string"
		) {
			// Extract raw numeric value from formatted string
			let raw = column._value !== undefined ? column._value : null;
			if (raw === null && data[column.fieldname] !== undefined) {
				raw = data[column.fieldname];
			}
			if (raw !== null && parseFloat(raw) < 0) {
				let abs_val = Math.abs(parseFloat(raw)).toLocaleString("ru-RU", {
					minimumFractionDigits: 0,
					maximumFractionDigits: 2,
				});
				value = `<span style="color:#c0392b;">(${abs_val})</span>`;
			}
		}

		return value;
	},
};
