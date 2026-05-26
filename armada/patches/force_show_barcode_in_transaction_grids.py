import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


CHILD_DOCTYPES = ("Sales Invoice Item", "Delivery Note Item", "Stock Entry Detail")
PARENT_DOCTYPES = ("Sales Invoice", "Delivery Note", "Stock Entry")


def execute():
	for doctype in CHILD_DOCTYPES:
		for prop, value, fieldtype in [
			("hidden", 0, "Check"),
			("in_list_view", 1, "Check"),
			("columns", 2, "Int"),
		]:
			make_property_setter(
				doctype,
				"barcode",
				prop,
				value,
				fieldtype,
				validate_fields_for_doctype=False,
			)

	for doctype in PARENT_DOCTYPES:
		frappe.clear_cache(doctype=doctype)
