frappe.listview_settings["Sales Order"] = {
	onload(listview) {
		render_qty_summary(listview);
	},
	refresh(listview) {
		render_qty_summary(listview);
	},
};

function render_qty_summary(listview) {
	const $label = ensure_summary_label(listview);

	// Exact filters the list is currently using (ID search, date range, etc.)
	const filters = (listview.get_filters_for_args() || []).slice();
	// Count drafts too (workflow: "Tasdiqqa jo'natish" => docstatus 0),
	// skip only cancelled orders
	filters.push(["Sales Order", "docstatus", "!=", 2]);

	// Guard against out-of-order async responses when filters change quickly
	const token = (listview.__qty_summary_token || 0) + 1;
	listview.__qty_summary_token = token;

	frappe.db
		.get_list("Sales Order", {
			filters: filters,
			// two aggregates => no ORDER BY
			fields: ["sum(total_qty) as total_qty", "sum(base_grand_total) as total_amount"],
			limit: 0,
		})
		.then((rows) => {
			if (listview.__qty_summary_token !== token) return; // a newer request started
			const total_qty = (rows && rows.length && rows[0].total_qty) || 0;
			const total_amount = (rows && rows.length && rows[0].total_amount) || 0;
			// Show qty as integer (no decimals) — orders are placed in whole items
			$label.find(".armada-qty-value").text(format_number(total_qty, null, 0));
			$label.find(".armada-amount-value").text(format_currency(total_amount, frappe.defaults.get_default("currency"), 0));
		});
}

function ensure_summary_label(listview) {
	const $form = listview.page.page_form;
	let $label = $form.find(".armada-qty-summary");
	if ($label.length) return $label;

	$label = $(`
		<div class="armada-qty-summary text-muted"
			style="display:flex;align-items:center;white-space:nowrap;margin-left:15px;gap:4px;font-size:12px;">
			<span>${__("Zakaz miqdori")}:</span>
			<b class="armada-qty-value" style="color:var(--text-color);margin-left:4px;">0</b>
			<span style="margin-left:12px;">${__("Summasi")}:</span>
			<b class="armada-amount-value" style="color:var(--text-color);margin-left:4px;">0</b>
		</div>
	`);

	const $std = $form.find(".standard-filter-section");
	if ($std.length) {
		$std.after($label);
	} else {
		$form.append($label);
	}
	return $label;
}
