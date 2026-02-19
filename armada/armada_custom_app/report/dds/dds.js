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
        },
        {
            "fieldname": "party_type",
            "label": __("Контрагент тури"),
            "fieldtype": "Select",
            "options": "\nCustomer\nSupplier\nEmployee",
            "on_change": function() {
                frappe.query_report.set_filter_value('party', '');
            }
        },
        {
            "fieldname": "party",
            "label": __("Контрагент"),
            "fieldtype": "Dynamic Link",
            "options": "party_type",
            "get_options": function() {
                return frappe.query_report.get_filter_value('party_type');
            }
        },
        {
            "fieldname": "expense_account",
            "label": __("Расход аккаунт"),
            "fieldtype": "Link",
            "options": "Account",
            "get_query": function() {
                return {
                    filters: {
                        "root_type": "Expense",
                        "is_group": 0
                    }
                };
            }
        },
        {
            "fieldname": "dividend_account",
            "label": __("Дивиденд аккаунт"),
            "fieldtype": "Link",
            "options": "Account",
            "get_query": function() {
                return {
                    filters: {
                        "root_type": "Equity",
                        "is_group": 0
                    }
                };
            }
        },
        {
            "fieldname": "show_transfers",
            "label": __("Перемещения"),
            "fieldtype": "Check",
            "default": 1
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
