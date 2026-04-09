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

// ─── PATCH ───────────────────────────────────────────────────────
armada_custom.apply_patch = function () {
    if (
        frappe.query_reports?.["Gross Profit"] &&
        !frappe.query_reports["Gross Profit"].__armada_patched
    ) {
        frappe.query_reports["Gross Profit"].formatter = armada_custom.integer_formatter;
        frappe.query_reports["Gross Profit"].__armada_patched = true;
        window._armada_col_logged = false; // reset log
        console.info("[Armada] ✓ Gross Profit patched");
        return true;
    }
    return false;
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
