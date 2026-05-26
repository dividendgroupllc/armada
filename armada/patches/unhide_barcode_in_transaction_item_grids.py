import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


CHILD_DOCTYPES = ("Sales Invoice Item", "Delivery Note Item", "Stock Entry Detail")
PARENT_DOCTYPES = ("Sales Invoice", "Delivery Note", "Stock Entry")


def execute():
	for doctype in CHILD_DOCTYPES:
		make_property_setter(
			doctype,
			"barcode",
			"hidden",
			0,
			"Check",
			validate_fields_for_doctype=False,
		)
		make_property_setter(
			doctype,
			"barcode",
			"in_list_view",
			1,
			"Check",
			validate_fields_for_doctype=False,
		)
		make_property_setter(
			doctype,
			"barcode",
			"columns",
			2,
			"Int",
			validate_fields_for_doctype=False,
		)
		make_property_setter(
			doctype,
			"barcode",
			"idx",
			2,
			"Int",
			validate_fields_for_doctype=False,
		)

	for doctype in PARENT_DOCTYPES:
		frappe.clear_cache(doctype=doctype)
