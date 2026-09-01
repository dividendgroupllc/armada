// Har bir hujjat turiga standart submit soati (yangi hujjatda avtomatik
// qo'yiladi, foydalanuvchi xohlasa o'zgartiradi):
//   Purchase Receipt        09:00
//   Stock Entry (transfer)  -> Склад Производство 10:00, -> Склад ГП 14:00
//   Production Entry        12:00 (o'z JS'ida — production_entry.js)
//   Delivery Note           16:00
// Stock Entry omborlari: Chiqim peremesheniya (from=Производство) yoki
// tayyor mahsulot kirimi (to=ГП) dan ochilsa Производство -> ГП,
// aks holda (Kirim peremesheniya ham) Сырьё -> Производство.
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
		if (!yangi(frm) || frm.doc.purpose !== "Material Transfer") return;
		const t = frm.doc.to_warehouse || "";
		for (const [prefix, vaqt] of OMBOR_SOAT) {
			if (t.startsWith(prefix)) {
				set_vaqt(frm, vaqt);
				return;
			}
		}
	}

	// Yangi hujjat qaysi ro'yxatdan (workspace shortcutdan) ochilganini aniqlaymiz.
	// Frappe from/to_warehouse'ni (no_copy) filtrdan yangi hujjatga o'tkazmaydi,
	// shuning uchun ro'yxat filtrlarini o'zimiz o'qiymiz.
	function kelgan_filtrlar() {
		try {
			const prev = frappe.get_prev_route ? frappe.get_prev_route() : [];
			if (prev[0] !== "List" || prev[1] !== "Stock Entry") return null;
			if (!window.cur_list || cur_list.doctype !== "Stock Entry" || !cur_list.filter_area)
				return null;
			// Warehouse daraxt bo'lgani uchun ro'yxat "=" ni
			// "descendants of (inclusive)" ga aylantiradi — ikkalasini ham olamiz
			const op = ["=", "descendants of (inclusive)", "descendants of"];
			const out = {};
			cur_list.filter_area.get().forEach((f) => {
				if (op.includes(f[2])) out[f[1]] = f[3];
			});
			return out;
		} catch (e) {
			return null;
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
		let manba = "Склад Сырьё";
		let maqsad = "Склад Производство";

		// Chiqim peremesheniya (from=Производство) yoki tayyor mahsulot kirimi
		// (to=ГП) dan kelgan bo'lsa — yo'nalish: Склад Производство -> Склад ГП.
		// Kirim peremesheniya (to=Производство) esa standartda qoladi:
		// Склад Сырьё -> Склад Производство.
		const filt = kelgan_filtrlar();
		if (filt) {
			const s = filt.from_warehouse || "";
			const t = filt.to_warehouse || "";
			if (s.startsWith("Склад Производство") || t.startsWith("Склад ГП")) {
				manba = "Склад Производство";
				maqsad = "Склад ГП";
			}
		}

		frappe.db
			.get_list("Warehouse", {
				filters: { warehouse_name: ["in", [manba, maqsad]] },
				fields: ["name", "warehouse_name"],
			})
			.then((omborlar) => {
				// foydalanuvchi bu orada o'zi tanlab ulgurgan bo'lsa — tegmaymiz
				if (!yangi(frm) || frm.doc.from_warehouse || frm.doc.to_warehouse) return;
				const map = {};
				(omborlar || []).forEach((w) => (map[w.warehouse_name] = w.name));
				if (map[manba]) frm.set_value("from_warehouse", map[manba]);
				if (map[maqsad]) frm.set_value("to_warehouse", map[maqsad]);
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
