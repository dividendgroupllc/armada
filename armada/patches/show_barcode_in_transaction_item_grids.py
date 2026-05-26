import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


CHILD_DOCTYPES = ("Sales Invoice Item", "Delivery Note Item", "Stock Entry Detail")


def execute():
	for doctype in CHILD_DOCTYPES:
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

	frappe.clear_cache(doctype="Sales Invoice")
	frappe.clear_cache(doctype="Delivery Note")
	frappe.clear_cache(doctype="Stock Entry")
