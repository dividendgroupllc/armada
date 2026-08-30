# Frappe grid ustunlari jami 11 birlikka sig'adi, ortig'i ko'rinmaydi.
# Mavjud default gridlar to'la bo'lgani uchun "Остаток на дату" ustuni
# sig'ishi uchun kam ishlatiladigan ustunlarni default ko'rinishdan olamiz
# (qator ochilganda baribir ko'rinadi). Shaxsiy GridView sozlamasi bor
# foydalanuvchilarga bu ta'sir qilmaydi — ular ustunni o'zi qo'shadi.
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PROPERTY_SETTERS = [
	# (child_doctype, fieldname, prop, value, fieldtype)
	("Purchase Receipt Item", "rejected_qty", "in_list_view", 0, "Check"),
	("Purchase Receipt Item", "net_amount", "in_list_view", 0, "Check"),
	("Purchase Receipt Item", "warehouse", "in_list_view", 0, "Check"),
	("Purchase Invoice Item", "rate", "columns", 2, "Int"),
	("Delivery Note Item", "uom", "in_list_view", 0, "Check"),
	("Delivery Note Item", "amount", "in_list_view", 0, "Check"),
	("Delivery Note Item", "warehouse", "in_list_view", 0, "Check"),
	("Sales Invoice Item", "item_code", "columns", 3, "Int"),
	("Sales Invoice Item", "amount", "in_list_view", 0, "Check"),
	("Sales Invoice Item", "warehouse", "in_list_view", 0, "Check"),
	# barcode'ni armada patchi 2 qilgan edi — SE gridida joy uchun 1 ga
	("Stock Entry Detail", "barcode", "columns", 1, "Int"),
]

PARENTS = ("Purchase Receipt", "Purchase Invoice", "Delivery Note", "Sales Invoice", "Stock Entry")


def execute():
	for doctype, fieldname, prop, value, fieldtype in PROPERTY_SETTERS:
		make_property_setter(
			doctype, fieldname, prop, value, fieldtype, validate_fields_for_doctype=False
		)

	# custom_ombor_qoldiq Stock Entry'da qty yonida tursin (avval t_warehouse
	# yonida yaratilgan)
	cf_name = "Stock Entry Detail-custom_ombor_qoldiq"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.db.set_value("Custom Field", cf_name, "insert_after", "qty")

	for doctype in PARENTS:
		frappe.clear_cache(doctype=doctype)
