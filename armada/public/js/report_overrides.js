frappe.provide("armada_custom");

armada_custom.integer_formatter = function (value, row, column, data, default_formatter) {

    if (value === null || value === undefined || value === "") {
        return default_formatter(value, row, column, data);
    }

    const num = parseFloat(value);
    if (isNaN(num)) {
        return default_formatter(value, row, column, data);
    }

    const rounded = Math.round(num);
    const color = num < 0 ? "color:var(--red-500);" : "";
    const align = "display:block;text-align:right;";

    // Column index bo'yicha aniqlash — eng ishonchli usul
    // Gross Profit report kolonlari tartibi:
    // 0:item_group, 1:brand, 2:item_code, 3:warehouse
    // 4:qty, 5:avg_selling, 6:valuation, 7:selling_amount
    // 8:buying_amount, 9:gross_profit, 10:gross_profit_percent

    const col_idx = column.colIndex !== undefined ? column.colIndex : -1;
    const fname = String(column.fieldname || column.id || column.name || col_idx).toLowerCase();
    const ftype = String(column.fieldtype || "").toLowerCase();
    const label = String(column.label || "").toLowerCase();

    // LOG — birinchi chaqiruvda
    if (!window._armada_col_logged) {
        console.warn("[ARMADA COL DUMP]", JSON.stringify({
            fieldname: column.fieldname,
            fieldtype: column.fieldtype,
            id: column.id,
            name: column.name,
            label: column.label,
            colIndex: column.colIndex,
            col_keys: Object.keys(column)
        }));
        window._armada_col_logged = true;
    }

    // PERCENT — barcha mumkin bo'lgan nomlar
    const PERCENT_NAMES = ["percent", "gross_profit_percent", "gross profit percent"];
    if (
        ftype === "percent" ||
        PERCENT_NAMES.some(p => fname.includes(p)) ||
        PERCENT_NAMES.some(p => label.includes(p))
    ) {
        return `<span style="${align}${color}">${rounded}%</span>`;
    }

    // QTY
    if (fname === "qty" || label === "qty" || fname === "stock_qty") {
        return `<span style="${align}${color}">${rounded}</span>`;
    }

    // CURRENCY / MONEY FIELDS
    const MONEY_NAMES = ["amount","price","profit","valuation","selling","buying","avg_sell"];
    if (
        ftype === "currency" ||
        MONEY_NAMES.some(m => fname.includes(m)) ||
        MONEY_NAMES.some(m => label.includes(m))
    ) {
        return `<span style="${align}${color}">$ ${rounded.toLocaleString("en-US")}</span>`;
    }

    // FLOAT / INT
    if (ftype === "float" || ftype === "int") {
        return `<span style="${align}${color}">${rounded}</span>`;
    }

    return default_formatter(value, row, column, data);
};

// ─── TOTAL FOOTER ────────────────────────────────────────────────
// Skript qo'shadigan "Total" qatori oddiy data qatori bo'lgani uchun
// kolonka filtri yozilganda yashirinib qolardi. Uning o'rniga datatable'ning
// showTotalRow footer'ini yoqamiz — u ko'rinayotgan (filtrlangan) qatorlar
// bo'yicha har safar qayta hisoblanadi va pastda doim turadi.

// O'rtacha/foiz ustunlar oddiy yig'indi bo'lmasligi kerak:
// fieldname -> [surat, maxraj] (weighted: sum(surat)/sum(maxraj))
armada_custom.GP_WEIGHTED_COLUMNS = {
    "avg._selling_rate": ["selling_amount", "qty"],
    "valuation_rate": ["buying_amount", "qty"],
    "gross_profit_%": ["gross_profit", "selling_amount"],
};

armada_custom.gp_column_total = function (values, cell) {
    const col = cell.column || {};
    const fname = col.fieldname || col.id;
    const weighted = armada_custom.GP_WEIGHTED_COLUMNS[fname];

    if (weighted) {
        let num = 0;
        let den = 0;
        (this.bodyRenderer.visibleRows || []).forEach((row) => {
            row.forEach((c) => {
                const f = c.column && (c.column.fieldname || c.column.id);
                if (f === weighted[0]) num += flt(c.content);
                else if (f === weighted[1]) den += flt(c.content);
            });
        });
        if (!den) return "";
        const value = num / den;
        return fname === "gross_profit_%" ? value * 100 : value;
    }

    return frappe.utils.report_column_total.call(this, values, cell);
};

armada_custom.gp_datatable_options = function (options) {
    options = options || {};
    // prepare_columns ichida bo'sh {} bilan ham chaqiriladi — himoya
    if (!Array.isArray(options.data) || !options.columns || !options.columns.length) {
        return options;
    }

    let group_by = null;
    try {
        group_by = frappe.query_report.get_filter_value("group_by");
    } catch (e) {
        return options;
    }

    // Invoice group'lashda qatorlar ikki darajali (indent) — footer yig'indisi
    // ikki barobar bo'lib ketadi, shuning uchun faqat boshqa group'lashlarda.
    const use_footer = Boolean(group_by && group_by !== "Invoice");
    // Doim boolean qo'yamiz: showTotalRow (false) !== add_total_row (0) bo'lgani
    // uchun query_report datatable'ni har safar qayta yaratadi va group_by
    // almashganda bu funksiya qayta ishlaydi.
    options.showTotalRow = use_footer;
    if (!use_footer) return options;

    // Skriptning o'z "Total" qatorini olib tashlaymiz — footer o'zi hisoblaydi.
    const first_field = options.columns[0].id || options.columns[0].fieldname;
    options.data = options.data.filter((row) => row && row[first_field] !== "Total");
    options.hooks = Object.assign({}, options.hooks, {
        columnTotal: armada_custom.gp_column_total,
    });
    return options;
};

// CSV export va Print/PDF standart yo'lda footer'ni faqat add_total_row=1 da
// qo'shadi; bizda u 0 (aks holda server ikkinchi total qo'shadi), shuning
// uchun footer qatorini o'zimiz qo'shamiz. Boshqa reportlarga ta'sir qilmaydi.
armada_custom.patch_total_export = function () {
    const qr = frappe.query_report;
    if (!qr || qr.__armada_total_export_patched) return Boolean(qr && qr.__armada_total_export_patched);
    qr.__armada_total_export_patched = true;

    const needs_footer = () =>
        qr.datatable &&
        qr.datatable.options.showTotalRow &&
        !qr.raw_data.add_total_row;

    const orig_csv = qr.get_data_for_csv.bind(qr);
    qr.get_data_for_csv = function (include_indentation) {
        const rows = orig_csv(include_indentation);
        if (needs_footer()) {
            const std = qr.datatable.datamanager.getStandardColumnCount();
            const total_row = qr.datatable.bodyRenderer
                .getTotalRow()
                .slice(std)
                .map((cell) => cell.content ?? "");
            if (!total_row[0]) total_row[0] = __("Total");
            rows.push(total_row);
        }
        return rows;
    };

    const orig_print = qr.get_data_for_print.bind(qr);
    qr.get_data_for_print = function () {
        const rows = orig_print();
        if (needs_footer() && rows.length) {
            const total_row = qr.datatable.bodyRenderer.getTotalRow().reduce((row, cell) => {
                if (cell.column.id) row[cell.column.id] = cell.content;
                row.is_total_row = true;
                return row;
            }, {});
            const first_field = qr.columns?.[0]?.id;
            if (first_field && !total_row[first_field]) total_row[first_field] = __("Total");
            if (!total_row.currency && rows[0].currency) total_row.currency = rows[0].currency;
            rows.push(total_row);
        }
        return rows;
    };
    return true;
};

// ─── PATCH ───────────────────────────────────────────────────────
armada_custom.apply_patch = function () {
    let report_patched = false;
    if (frappe.query_reports?.["Gross Profit"]) {
        if (!frappe.query_reports["Gross Profit"].__armada_patched) {
            frappe.query_reports["Gross Profit"].formatter = armada_custom.integer_formatter;
            frappe.query_reports["Gross Profit"].get_datatable_options =
                armada_custom.gp_datatable_options;
            frappe.query_reports["Gross Profit"].__armada_patched = true;
            window._armada_col_logged = false; // reset log
            console.info("[Armada] ✓ Gross Profit patched");
        }
        report_patched = true;
    }
    const export_patched = armada_custom.patch_total_export();
    return report_patched && export_patched;
};

// ─── ROUTE WATCHER ───────────────────────────────────────────────
frappe.router.on("change", function () {
    const route = frappe.get_route();

    if (route[0] !== "query-report" || route[1] !== "Gross Profit") {
        if (frappe.query_reports?.["Gross Profit"]) {
            delete frappe.query_reports["Gross Profit"].__armada_patched;
        }
        return;
    }

    if (armada_custom.apply_patch()) return;

    let attempts = 0;
    const poller = setInterval(function () {
        if (armada_custom.apply_patch() || ++attempts >= 50) {
            clearInterval(poller);
        }
    }, 200);
});
