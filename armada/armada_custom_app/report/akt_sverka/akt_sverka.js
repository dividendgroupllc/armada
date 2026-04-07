frappe.query_reports["Akt Sverka"] = {
    "after_datatable_render": function(datatable_obj) {
        try {
            var report = frappe.query_report;
            var html = report && report.report_doc ? null : null;
            // message slotidagi summary HTML ni olish
            var msg = report && report.message ? report.message : null;
            if (!msg && report && report.raw_data) {
                msg = report.raw_data.message;
            }
            var $area = report.$report.find('.akt-sverka-summary');
            if (!$area.length) {
                $area = $('<div class="akt-sverka-summary"></div>');
                report.$report.prepend($area);
            }
            if (msg) {
                $area.html(msg).show();
            } else {
                $area.empty().hide();
            }
        } catch (e) {
            console.error('Akt Sverka summary render error:', e);
        }
    },
    "onload": function(report) {
        // Add back button to return to Kontragent Otchet
        report.page.add_inner_button(__("Контрагент Отчётга Қайтиш"), function() {
            var from_date = frappe.query_report.get_filter_value('from_date');
            var to_date = frappe.query_report.get_filter_value('to_date');
            var party_type = frappe.query_report.get_filter_value('party_type');

            // Redirect to Kontragent Otchet with filters
            var url = `/app/query-report/Kontragent Otchet?from_date=${from_date}&to_date=${to_date}`;
            if (party_type) {
                url += `&party_type=${encodeURIComponent(party_type)}`;
            }
            frappe.set_route('query-report', 'Kontragent Otchet', {
                from_date: from_date,
                to_date: to_date,
                party_type: party_type || ''
            });
        });
    },
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
            "fieldname": "party_type",
            "label": __("Контрагент тури"),
            "fieldtype": "Select",
            "options": "\nCustomer\nSupplier\nEmployee\nOther",
            "default": "Customer",
            "reqd": 1
        },
        {
            "fieldname": "party",
            "label": __("Контрагент"),
            "fieldtype": "Dynamic Link",
            "reqd": 1,
            "get_options": function() {
                var party_type = frappe.query_report.get_filter_value('party_type');
                var party = frappe.query_report.get_filter_value('party');
                if(party && !party_type) {
                    frappe.throw(__("Please select Party Type first"));
                }
                return party_type;
            }
        }
    ],
    
    "formatter": function(value, row, column, data, default_formatter) {
        // Dollar belgisini olib tashlash
        value = default_formatter(value, row, column, data);
        
        // Currency fieldlarida $ ni olib tashlash
        if (column.fieldtype == "Currency" && value) {
            value = value.replace(/\$/g, '');
        }
        
        // Total qatorini highlight qilish
        if (data && data.voucher_type === "Total") {
            value = `<span style="font-weight: bold; background-color: #e3f2fd;">${value}</span>`;
        }
        
        return value;
    }
}
