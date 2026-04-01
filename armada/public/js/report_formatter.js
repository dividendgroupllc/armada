// public/js/report_formatter.js
frappe.armada = frappe.armada || {};

frappe.armada.currency_formatter = function (
    value, row, column, data, default_formatter, precision
) {
    value = default_formatter(value, row, column, data);

    if (column.fieldtype === "Currency") {
        var raw = data[column.fieldname];
        if (typeof raw === "number") {
            var p = precision !== undefined ? precision : 0;
            var rounded = p === 0
                ? Math.round(raw)
                : parseFloat(raw.toFixed(p));
            return format_currency(
                rounded,
                data.currency || frappe.defaults.get_default("currency"),
                p
            );
        }
    }
    return value;
};
