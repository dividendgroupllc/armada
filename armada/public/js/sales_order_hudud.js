// "Hudud": eskirgan "Viloyat" varianti faqat shu qiymat bilan saqlangan
// eski zakazlarda ko'rinadi; yangi zakazlarda aniq viloyat tanlanadi.
const ESKI_HUDUD = "Viloyat";

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		const df = frappe.meta.get_docfield("Sales Order", "custom_hudud");
		if (!df) return;

		// Eski zakazdan nusxa olinganda (amend emas) eskirgan qiymatni tozalaymiz.
		if (frm.is_new() && !frm.doc.amended_from && frm.doc.custom_hudud === ESKI_HUDUD) {
			frm.set_value("custom_hudud", "");
		}

		const options = (df.options || "").split("\n");
		frm.set_df_property(
			"custom_hudud",
			"options",
			frm.doc.custom_hudud === ESKI_HUDUD ? options : options.filter((o) => o !== ESKI_HUDUD)
		);
	},
});
