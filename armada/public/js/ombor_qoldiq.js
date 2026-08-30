// "Остаток на дату" — hujjat qatorida ombor qoldig'ini hujjatning
// posting_date + posting_time bo'yicha ko'rsatadi (custom_ombor_qoldiq maydoni).
// Bitta fayl 5 ta doctype'ga ulangan (hooks.doctype_js) va har birida qayta
// evaluatsiya bo'ladi — shuning uchun window guard bilan faqat bir marta
// ro'yxatdan o'tkazamiz.
(function () {
	if (window.__armada_ombor_qoldiq) return;
	window.__armada_ombor_qoldiq = true;

	const DOCTYPES = {
		"Purchase Receipt": "Purchase Receipt Item",
		"Purchase Invoice": "Purchase Invoice Item",
		"Delivery Note": "Delivery Note Item",
		"Sales Invoice": "Sales Invoice Item",
		"Stock Entry": "Stock Entry Detail",
	};

	function row_warehouse(row) {
		// Stock Entry'da s_warehouse/t_warehouse, qolganlarida warehouse
		return row.warehouse || row.s_warehouse || row.t_warehouse || null;
	}

	function update_all(frm) {
		if (!frm.doc || frm.doc.docstatus !== 0) return;

		// Tez ketma-ket triggerlarni bitta so'rovga yig'ish
		if (frm.__qoldiq_timer) clearTimeout(frm.__qoldiq_timer);
		frm.__qoldiq_timer = setTimeout(() => _fetch(frm), 250);
	}

	function _fetch(frm) {
		const items = (frm.doc.items || [])
			.filter((r) => r.item_code && row_warehouse(r))
			.map((r) => ({
				name: r.name,
				item_code: r.item_code,
				warehouse: row_warehouse(r),
			}));
		if (!items.length) return;

		// Faqat eng oxirgi so'rov javobi qabul qilinadi (eski javob yangisini
		// yozib qo'ymasligi uchun)
		const req_id = (frm.__qoldiq_req = (frm.__qoldiq_req || 0) + 1);
		frappe.call({
			method: "armada.armada_custom_app.ombor_qoldiq.get_qoldiqlar",
			args: {
				items: items,
				posting_date: frm.doc.posting_date,
				posting_time: frm.doc.posting_time,
			},
			callback(r) {
				if (req_id !== frm.__qoldiq_req || !r.message) return;
				(frm.doc.items || []).forEach((row) => {
					if (row.name in r.message) {
						// to'g'ridan-to'g'ri yozamiz — forma "dirty" bo'lmasin
						row.custom_ombor_qoldiq = r.message[row.name];
					}
				});
				frm.refresh_field("items");
			},
		});
	}

	const parent_events = {
		refresh: update_all,
		posting_date: update_all,
		posting_time: update_all,
		set_posting_time: update_all,
	};

	const child_events = {};
	["item_code", "warehouse", "s_warehouse", "t_warehouse"].forEach((field) => {
		child_events[field] = (frm) => update_all(frm);
	});

	Object.entries(DOCTYPES).forEach(([parent, child]) => {
		frappe.ui.form.on(parent, parent_events);
		frappe.ui.form.on(child, child_events);
	});
})();
