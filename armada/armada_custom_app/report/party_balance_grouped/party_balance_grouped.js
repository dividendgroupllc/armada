// Party Balance Grouped — Full Balance Sheet Replacement
// ERPNext v15 | Armada Custom App
// Production-ready version v2.1 — ERPNext-style default date handling.
//
// v2.1 changes vs v2:
//   D1 — period_end_date filter: added default = frappe.datetime.get_today()
//   D2 — _sync_filter_display: auto-fills date fields when switching to
//         "Date Range" mode — mirrors ERPNext native Balance Sheet behaviour.
//         - period_end_date  ← today (if currently empty)
//         - period_start_date ← fiscal year start from from_fiscal_year filter
//           (falls back to Jan 1 of current calendar year if no FY selected)
//   No other changes. Python file untouched.
//
// Previous fixes (v2) still in place:
//   F1 — toggle_filter_display logic was inverted (hidden param misused)
//   F2 — onload now syncs filter display state immediately
//   F3 — frappe.utils.cstr() (non-existent) replaced with String()
//   F4 — "::" separator replaced with "§§" (U+00A7) to match Python

// ── Separator must match Python SEP constant ─────────────────────────────────
const PARTY_SEP = "\u00a7\u00a7"; // §§

frappe.query_reports["Party Balance Grouped"] = {

	// ── Onload: set fiscal year defaults + sync filter visibility ─────────────
	//
	// Behaviour mirrors ERPNext native Balance Sheet:
	//   1. Read user's default fiscal year.
	//   2. Fetch that FY's start/end dates from DB.
	//   3. Push all values into filters (FY pickers + hidden date fields).
	//   4. Sync which filter rows are visible.
	//
	// If no fiscal year default exists (fresh install / misconfigured system):
	//   - Switch to "Date Range" mode automatically.
	//   - period_end_date  = today.
	//   - period_start_date = January 1 of the current calendar year.
	//   This guarantees the report is always runnable on first load.
	onload: function (report) {
		let fiscal_year = frappe.defaults.get_user_default("fiscal_year");

		if (fiscal_year) {
			frappe.db
				.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
				.then((r) => {
					if (r && r.message) {
						frappe.query_report.set_filter_value({
							from_fiscal_year:  fiscal_year,
							to_fiscal_year:    fiscal_year,
							period_start_date: r.message.year_start_date,
							period_end_date:   r.message.year_end_date,
							filter_based_on:   "Fiscal Year",
						});
					}
					// F2 fix: sync display state AFTER defaults are applied
					_sync_filter_display();
				});
		} else {
			// No fiscal year configured — fall back to Date Range / current year
			let today = frappe.datetime.get_today();
			let year_start = today.split("-")[0] + "-01-01";
			frappe.query_report.set_filter_value({
				filter_based_on:   "Date Range",
				period_start_date: year_start,
				period_end_date:   today,
			});
			_sync_filter_display();
		}
	},

	// ── Tree configuration ────────────────────────────────────────────────────
	tree:          true,
	name_field:    "account",
	parent_field:  "parent_account",
	initial_depth: 3,

	// ── Filters ───────────────────────────────────────────────────────────────
	filters: [
		{
			fieldname: "company",
			label:     __("Company"),
			fieldtype: "Link",
			options:   "Company",
			default:   frappe.defaults.get_user_default("Company"),
			reqd:      1,
		},
		{
			fieldname: "filter_based_on",
			label:     __("Filter Based On"),
			fieldtype: "Select",
			options:   ["Fiscal Year", "Date Range"],
			default:   "Fiscal Year",
			reqd:      1,
			on_change: function () {
				_sync_filter_display();
			},
		},
		{
			// D1: default = today so the field is never blank when revealed
			fieldname: "period_start_date",
			label:     __("Start Date"),
			fieldtype: "Date",
			hidden:    1,
		},
		{
			// D1: default = today so the field is never blank when revealed
			fieldname: "period_end_date",
			label:     __("End Date"),
			fieldtype: "Date",
			hidden:    1,
			default:   frappe.datetime.get_today(),
		},
		{
			fieldname: "from_fiscal_year",
			label:     __("Start Year"),
			fieldtype: "Link",
			options:   "Fiscal Year",
			default:   frappe.defaults.get_user_default("fiscal_year"),
			on_change: function () {
				let fy = frappe.query_report.get_filter_value("from_fiscal_year");
				if (!fy) return;
				frappe.db.get_value("Fiscal Year", fy, "year_start_date").then((r) => {
					if (r && r.message) {
						frappe.query_report.set_filter_value({
							period_start_date: r.message.year_start_date,
						});
					}
				});
			},
		},
		{
			fieldname: "to_fiscal_year",
			label:     __("End Year"),
			fieldtype: "Link",
			options:   "Fiscal Year",
			default:   frappe.defaults.get_user_default("fiscal_year"),
			on_change: function () {
				let fy = frappe.query_report.get_filter_value("to_fiscal_year");
				if (!fy) return;
				frappe.db.get_value("Fiscal Year", fy, "year_end_date").then((r) => {
					if (r && r.message) {
						frappe.query_report.set_filter_value({
							period_end_date: r.message.year_end_date,
						});
					}
				});
			},
		},
		{
			fieldname: "periodicity",
			label:     __("Periodicity"),
			fieldtype: "Select",
			options: [
				{ value: "Monthly",     label: __("Monthly") },
				{ value: "Quarterly",   label: __("Quarterly") },
				{ value: "Half-Yearly", label: __("Half-Yearly") },
				{ value: "Yearly",      label: __("Yearly") },
			],
			default: "Yearly",
			reqd:    1,
		},
		{
			fieldname: "accumulated_values",
			label:     __("Accumulated Values"),
			fieldtype: "Check",
			default:   1,
		},
		{
			fieldname: "cost_center",
			label:     __("Cost Center"),
			fieldtype: "MultiSelectList",
			options:   "Cost Center",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "finance_book",
			label:     __("Finance Book"),
			fieldtype: "Link",
			options:   "Finance Book",
		},
		{
			fieldname: "include_default_book_entries",
			label:     __("Include Default Book Entries"),
			fieldtype: "Check",
			default:   1,
		},
		{
			fieldname: "show_zero_balance",
			label:     __("Show Zero Balance Parties"),
			fieldtype: "Check",
			default:   1,
		},
	],

	// ── Formatter ─────────────────────────────────────────────────────────────
	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		let indent  = data.indent || 0;
		let is_grp  = data.is_group;
		let acc     = String(data.account || "");

		// F4 fix: detect party rows using §§ separator (matches Python SEP)
		let is_party_group = is_grp && acc.includes(PARTY_SEP);
		let is_party_leaf  = !is_grp && acc.includes(PARTY_SEP);

		if (column.fieldname === "account") {
			// F4 fix: split on §§, take the last segment for display label
			let parts = acc.split(PARTY_SEP);
			let label = parts[parts.length - 1] || String(value);
			let clean = frappe.utils.escape_html(label);

			if (is_party_group) {
				return `<span style="
					font-weight: 500;
					color: var(--text-on-light-green, #1a7f5e);
					padding-left: ${indent * 8}px;
				">\uD83D\uDCC2 ${clean}</span>`;
			}

			if (is_party_leaf) {
				return `<span style="
					color: var(--text-muted);
					padding-left: ${indent * 8}px;
				">&bull; ${clean}</span>`;
			}
		}

		// Currency: red if negative
		if (column.fieldtype === "Currency" && flt(value) < 0) {
			let formatted = default_formatter(value, row, column, data);
			return `<span style="color: var(--red-500, #e53e3e);">${formatted}</span>`;
		}

		// Root section rows (indent=0, is_group=true) — bold
		if (indent === 0 && is_grp) {
			let formatted = default_formatter(value, row, column, data);
			return `<strong style="font-size: 13px;">${formatted}</strong>`;
		}

		return default_formatter(value, row, column, data);
	},
};


// ── Helper: sync filter display state ─────────────────────────────────────────
//
// F1 + F2 fix: centralised function called both on_change and onload.
// toggle_filter_display(fieldname, hidden):
//   hidden = false → field is VISIBLE
//   hidden = true  → field is HIDDEN
//
// D2 fix: when switching TO "Date Range" mode, auto-fill the date fields
// if they are currently empty.
//   period_end_date   ← today
//   period_start_date ← year_start_date of the currently selected from_fiscal_year
//                       (falls back to Jan 1 of current calendar year)
//
// Rationale: ERPNext native Balance Sheet always shows a ready-to-run report
// on first open. Our report must behave identically.
function _sync_filter_display() {
	let v    = frappe.query_report.get_filter_value("filter_based_on");
	let isFY = (v === "Fiscal Year");

	// Fiscal Year mode  → show FY pickers, hide date pickers
	// Date Range mode   → hide FY pickers, show date pickers
	frappe.query_report.toggle_filter_display("from_fiscal_year",  !isFY); // hidden=true when Date Range
	frappe.query_report.toggle_filter_display("to_fiscal_year",    !isFY);
	frappe.query_report.toggle_filter_display("period_start_date",  isFY); // hidden=true when Fiscal Year
	frappe.query_report.toggle_filter_display("period_end_date",    isFY);

	// D2: Auto-fill date fields when entering Date Range mode
	if (!isFY) {
		let today = frappe.datetime.get_today();

		// Fill period_end_date with today if blank
		if (!frappe.query_report.get_filter_value("period_end_date")) {
			frappe.query_report.set_filter_value("period_end_date", today);
		}

		// Fill period_start_date from the selected FY, or Jan 1 as fallback
		if (!frappe.query_report.get_filter_value("period_start_date")) {
			let fy = frappe.query_report.get_filter_value("from_fiscal_year");
			if (fy) {
				frappe.db.get_value("Fiscal Year", fy, "year_start_date").then((r) => {
					if (r && r.message && r.message.year_start_date) {
						frappe.query_report.set_filter_value(
							"period_start_date",
							r.message.year_start_date
						);
					} else {
						// FY record had no start date — fall back to Jan 1
						frappe.query_report.set_filter_value(
							"period_start_date",
							today.split("-")[0] + "-01-01"
						);
					}
				});
			} else {
				// No FY selected at all — Jan 1 of current year
				frappe.query_report.set_filter_value(
					"period_start_date",
					today.split("-")[0] + "-01-01"
				);
			}
		}
	}
}
