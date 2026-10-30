// "Долг поставщику" — Purchase Invoice qoralamasida tanlangan supplier'ning
// joriy qarzini ko'rsatadi (custom_supplier_qarz, virtual maydon).
frappe.ui.form.on("Purchase Invoice", {
	refresh: update_supplier_qarz,
	supplier: update_supplier_qarz,
	company: update_supplier_qarz,
});

function update_supplier_qarz(frm) {
	if (frm.doc.docstatus !== 0) return;
	if (!frm.doc.supplier || !frm.doc.company) {
		frm.doc.custom_supplier_qarz = null;
		frm.refresh_field("custom_supplier_qarz");
		return;
	}

	// Faqat eng oxirgi so'rov javobi qabul qilinadi
	const req_id = (frm.__qarz_req = (frm.__qarz_req || 0) + 1);
	frappe.call({
		method: "armada.armada_custom_app.supplier_qarz.get_supplier_qarz",
		args: { supplier: frm.doc.supplier, company: frm.doc.company },
		callback(r) {
			if (req_id !== frm.__qarz_req) return;
			// to'g'ridan-to'g'ri yozamiz — forma "dirty" bo'lmasin
			frm.doc.custom_supplier_qarz = r.message;
			frm.refresh_field("custom_supplier_qarz");
		},
	});
}
