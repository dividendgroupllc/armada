// Har bir hujjat turiga standart submit soati (yangi hujjatda avtomatik
// qo'yiladi, foydalanuvchi xohlasa o'zgartiradi):
//   Purchase Receipt        09:00
//   Stock Entry (transfer)  -> Склад Производство 10:00, -> Склад ГП 14:00
//   Production Entry        12:00 (o'z JS'ida — production_entry.js)
//   Delivery Note           16:00
// Bitta fayl bir nechta doctype'ga ulangan (hooks.doctype_js) — window guard
// bilan faqat bir marta ro'yxatdan o'tkazamiz.
(function () {
	if (window.__armada_default_vaqt) return;
	window.__armada_default_vaqt = true;

	const SOAT = {
		"Purchase Receipt": "09:00:00",
		"Delivery Note": "16:00:00",
	};

	// Stock Entry: maqsad ombor nomi shu bilan boshlansa -> shu soat
	const OMBOR_SOAT = [
		["Склад ГП", "14:00:00"],
		["Склад Производство", "10:00:00"],
	];

	function yangi(frm) {
		return frm.is_new() && !frm.doc.amended_from;
	}

	function set_vaqt(frm, vaqt) {
		// foydalanuvchi soatni qo'lda o'zgartirgan bo'lsa, boshqa tegmaymiz
		if (!yangi(frm) || frm.__vaqt_manual) return;
		frm.__vaqt_auto = vaqt;
		if (!frm.doc.set_posting_time) frm.set_value("set_posting_time", 1);
		frm.set_value("posting_time", vaqt);
	}

	const kuzatuv = {
		posting_time(frm) {
			if (
				frm.doc.posting_time &&
				frm.__vaqt_auto &&
				frm.doc.posting_time !== frm.__vaqt_auto
			) {
				frm.__vaqt_manual = true;
			}
		},
	};

	Object.entries(SOAT).forEach(([doctype, vaqt]) => {
		frappe.ui.form.on(doctype, {
			...kuzatuv,
			onload(frm) {
				if (yangi(frm)) set_vaqt(frm, vaqt);
			},
		});
	});

	// ---- Stock Entry ----

	function se_vaqt(frm) {
		if (frm.doc.purpose !== "Material Transfer") return;
		const t = frm.doc.to_warehouse || "";
		for (const [prefix, vaqt] of OMBOR_SOAT) {
			if (t.startsWith(prefix)) {
				set_vaqt(frm, vaqt);
				return;
			}
		}
	}

	function se_default_omborlar(frm) {
		if (!yangi(frm) || frm.doc.purpose !== "Material Transfer") return;

		const bosh =
			!frm.doc.from_warehouse &&
			!frm.doc.to_warehouse &&
			!(frm.doc.items || []).some((r) => r.item_code || r.s_warehouse || r.t_warehouse);
		if (!bosh) {
			se_vaqt(frm);
			return;
		}

		// standart yo'nalish: Склад Сырьё -> Склад Производство
		frappe.db
			.get_list("Warehouse", {
				filters: { warehouse_name: ["in", ["Склад Сырьё", "Склад Производство"]] },
				fields: ["name", "warehouse_name"],
			})
			.then((omborlar) => {
				const map = {};
				(omborlar || []).forEach((w) => (map[w.warehouse_name] = w.name));
				if (map["Склад Сырьё"]) frm.set_value("from_warehouse", map["Склад Сырьё"]);
				if (map["Склад Производство"])
					frm.set_value("to_warehouse", map["Склад Производство"]);
				se_vaqt(frm);
			});
	}

	frappe.ui.form.on("Stock Entry", {
		...kuzatuv,
		onload: se_default_omborlar,
		purpose: se_default_omborlar,
		to_warehouse: se_vaqt,
	});
})();
