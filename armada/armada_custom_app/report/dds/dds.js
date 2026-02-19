frappe.query_reports["DDS"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("Сана дан"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("Сана гача"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "mode_of_payment",
            "label": __("Способ оплаты"),
            "fieldtype": "Link",
            "options": "Mode of Payment"
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // Dollar belgisini olib tashlash
        if (column.fieldtype == "Currency" && value) {
            value = value.replace(/\$/g, '');
        }

        // Нач. остаток va ИТОГО qatorlarini bold qilish
        if (data && (data.is_opening || data.is_total)) {
            value = `<span style="font-weight: bold;">${value}</span>`;
        }

        return value;
    }
}
