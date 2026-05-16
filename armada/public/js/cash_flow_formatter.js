// cash_flow_formatter.js
// Rounds all Currency cells and summary cards in Cash Flow report to whole numbers.
// Depends on: report_formatter.js  (frappe.armada.currency_formatter + round_summary + patch_report)
// Load order in hooks.py:  report_formatter.js  →  cash_flow_formatter.js
(function () {
    "use strict";

    // Guard: report_formatter.js must be loaded first.
    if (!frappe.armada || typeof frappe.armada.patch_report !== "function") {
        console.error(
            "[Armada] cash_flow_formatter.js: frappe.armada.patch_report topilmadi. " +
            "hooks.py da report_formatter.js oldin yuklanganligi tekshiring."
        );
        return;
    }

    frappe.armada.patch_report("Cash Flow", function (reportConfig) {

        // ── 1. Original hook larni saqlash ──────────────────────────────────
        var _origOnload      = reportConfig.onload;
        var _origRefresh     = reportConfig.refresh;
        var _origAfterRender = reportConfig.after_datatable_render;

        // ── 2. Datatable cell formatter ─────────────────────────────────────
        // Har bir Currency ustunini 0 decimal bilan render qiladi.
        reportConfig.formatter = function (value, row, column, data, df) {
            return frappe.armada.currency_formatter(value, row, column, data, df, 0);
        };

        // ── 3. Onload — report birinchi ochilganda ──────────────────────────
        reportConfig.onload = function (report) {
            if (_origOnload) _origOnload.call(this, report);
            // DOM render uchun 300ms kutish — ERPNext summary kartlari kech chiqadi
            setTimeout(frappe.armada.round_summary, 300);
        };

        // ── 4. Refresh — filter o'zgarganda yoki ma'lumot qayta yuklanganda ─
        reportConfig.refresh = function (report) {
            if (_origRefresh) _origRefresh.call(this, report);
            // Refresh render onload dan sekinroq — 500ms
            setTimeout(frappe.armada.round_summary, 500);
        };

        // ── 5. After datatable render — kech render uchun qo'shimcha hook ───
        reportConfig.after_datatable_render = function (datatable) {
            if (_origAfterRender) _origAfterRender.call(this, datatable);
            // Datatable tayyor, summary biroz kechroq chiqadi — 200ms
            setTimeout(frappe.armada.round_summary, 200);
        };
    });

})();
