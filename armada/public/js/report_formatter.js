// report_formatter.js
// Shared utilities for Armada financial report customizations
// Works with: Balance Sheet, Profit and Loss Statement
(function () {
    "use strict";

    frappe.armada = frappe.armada || {};

    // ——— Currency formatter for datatable cells ———
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

    // ——— Summary card rounding (Total Asset, Total Liability, etc.) ———
    frappe.armada.round_summary = function () {
        $(".report-summary .summary-value").each(function () {
            var $el = $(this);
            var text = $el.text().trim();
            if (!text) return;

            // Already rounded — no decimal part longer than 2
            if ($el.data("armada-rounded")) return;

            var match = text.match(/^([^\d\-]*)([\d\s\.\,\-]+)$/);
            if (!match) return;

            var prefix = match[1];
            var numStr = match[2].trim();

            var cleaned = numStr
                .replace(/\s/g, "")
                .replace(/,/g, ".");

            var num = parseFloat(cleaned);
            if (isNaN(num)) return;

            var rounded = Math.round(num);
            var formatted = rounded.toLocaleString("fr-FR");

            $el.text(prefix + formatted);
            $el.data("armada-rounded", true);
        });
    };

    // ——— Trap-based report patcher ———
    // Uses Object.defineProperty to intercept EVERY write to
    // frappe.query_reports[reportName]. When Frappe's eval() creates
    // a new report config object, our setter fires and re-applies patches.
    frappe.armada.patch_report = function (reportName, patchFn) {
        var _storage = {};

        function _install_trap() {
            // If frappe.query_reports doesn't exist yet, wait
            if (!frappe.query_reports) {
                setTimeout(_install_trap, 50);
                return;
            }

            // Capture any existing value
            if (frappe.query_reports.hasOwnProperty(reportName)) {
                _storage[reportName] = frappe.query_reports[reportName];
            }

            // Delete existing property so defineProperty doesn't conflict
            try { delete frappe.query_reports[reportName]; } catch (e) {}

            Object.defineProperty(frappe.query_reports, reportName, {
                configurable: true,
                enumerable: true,
                get: function () {
                    return _storage[reportName];
                },
                set: function (newVal) {
                    _storage[reportName] = newVal;
                    // Re-apply patches every time Frappe overwrites this report
                    if (newVal && typeof newVal === "object") {
                        try {
                            patchFn(newVal);
                        } catch (e) {
                            console.error(
                                "[Armada] patch_report error for " + reportName + ":",
                                e
                            );
                        }
                    }
                }
            });

            // If value already existed, trigger patch now
            if (_storage[reportName]) {
                try {
                    patchFn(_storage[reportName]);
                } catch (e) {
                    console.error("[Armada] initial patch error for " + reportName + ":", e);
                }
            }
        }

        // Install as early as possible
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", _install_trap);
        } else {
            _install_trap();
        }
    };

})();
