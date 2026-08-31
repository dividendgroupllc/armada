# Stock Entry item jadvali default ustun tartibi va kengliklari
# (foydalanuvchi so'rovi bo'yicha):
#   Source Warehouse(1) -> Target Warehouse(1) -> Barcode(2) -> Item Code(1)
#   -> Qty(2) -> Basic Rate(2) -> Остаток на дату(1)  = jami 10 (byudjet 10)
# Eslatma: standart fieldlar tartibini "idx" property setter o'zgartirmaydi —
# faqat doctype darajasidagi "field_order" ishlaydi (Customize Form usuli).
import json

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

COLUMNS = [
	("s_warehouse", 1),
	("t_warehouse", 1),
	("barcode", 2),
	("item_code", 1),
	("qty", 2),
	("basic_rate", 2),
]


def execute():
	for fieldname, cols in COLUMNS:
		make_property_setter(
			"Stock Entry Detail", fieldname, "columns", cols, "Int",
			validate_fields_for_doctype=False,
		)

	# ishlamaydigan eski barcode idx setterlarini tozalaymiz
	frappe.db.delete(
		"Property Setter",
		{"doc_type": "Stock Entry Detail", "field_name": "barcode", "property": "idx"},
	)

	# Остаток на дату — eng oxirida (basic_rate'dan keyin), kengligi 1
	cf = "Stock Entry Detail-custom_ombor_qoldiq"
	if frappe.db.exists("Custom Field", cf):
		frappe.db.set_value("Custom Field", cf, {"insert_after": "basic_rate", "columns": 1})

	frappe.clear_cache(doctype="Stock Entry Detail")

	# to'liq tartib: barcode t_warehouse'dan keyin, Остаток basic_rate'dan keyin
	fieldnames = [f.fieldname for f in frappe.get_meta("Stock Entry Detail").fields]
	if "barcode" in fieldnames:
		fieldnames.remove("barcode")
		fieldnames.insert(fieldnames.index("t_warehouse") + 1, "barcode")
	if "custom_ombor_qoldiq" in fieldnames:
		fieldnames.remove("custom_ombor_qoldiq")
		fieldnames.insert(fieldnames.index("basic_rate") + 1, "custom_ombor_qoldiq")
	make_property_setter(
		"Stock Entry Detail", None, "field_order", json.dumps(fieldnames), "Data",
		for_doctype=True, validate_fields_for_doctype=False,
	)

	frappe.clear_cache(doctype="Stock Entry")
	frappe.clear_cache(doctype="Stock Entry Detail")
