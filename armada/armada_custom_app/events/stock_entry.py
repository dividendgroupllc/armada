import frappe
from frappe import _


def block_zero_valuation_repack(doc, method=None):
	"""Repack'da tayyor mahsulot 0 narx bilan omborga kirmasin.

	"Allow Zero Valuation Rate" belgisi Repack target qatorida yoqilsa, xom-ashyo
	qiymati 5119 Stock Adjustment'ga ketadi, tayyor mahsulot esa 0 tannarx bilan
	sotiladi (hisobotlarda 100% marja). Bu belgi Repack'da hech qachon kerak emas:
	tayyor mahsulot narxi xom-ashyo qiymatidan avtomatik hisoblanadi.
	"""
	if doc.purpose != "Repack":
		return

	rows = [
		d for d in doc.get("items") if d.t_warehouse and d.allow_zero_valuation_rate
	]
	if not rows:
		return

	frappe.throw(
		_(
			"Repack'da \"Allow Zero Valuation Rate\" belgisini yoqib bo'lmaydi — "
			"tayyor mahsulot narxi xom-ashyo qiymatidan hisoblanadi. "
			"Qatorlardan belgini olib tashlang: {0}"
		).format(", ".join(f"#{d.idx} {d.item_code}" for d in rows)),
		title=_("Repack: nol tannarx"),
	)
