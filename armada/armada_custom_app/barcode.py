import frappe
from frappe.model.naming import make_autoname


BARCODE_SERIES = "ARM.##########"
ITEM_BARCODE_PARENTFIELD = "barcodes"
ITEM_BARCODE_DISPLAY_FIELD = "custom_barcode"


def generate_item_barcode():
	"""Return the next unique internal item barcode."""
	for _attempt in range(20):
		barcode = make_autoname(BARCODE_SERIES)
		if not frappe.db.exists("Item Barcode", {"barcode": barcode}):
			return barcode

	frappe.throw("Could not generate a unique item barcode. Please try again.")


def ensure_item_barcode(doc, method=None):
	"""Add an internal barcode to a new Item when no barcode was provided."""
	if _has_barcode(doc):
		sync_item_barcode_display(doc)
		return

	doc.append(
		ITEM_BARCODE_PARENTFIELD,
		{
			"barcode": generate_item_barcode(),
			"uom": doc.stock_uom,
		},
	)
	sync_item_barcode_display(doc)


def sync_item_barcode_display(doc, method=None):
	"""Copy the first barcode into the Item detail display field."""
	if not frappe.get_meta("Item").has_field(ITEM_BARCODE_DISPLAY_FIELD):
		return

	doc.set(ITEM_BARCODE_DISPLAY_FIELD, get_first_item_barcode(doc))


def get_first_item_barcode(doc):
	for row in doc.get(ITEM_BARCODE_PARENTFIELD, []):
		barcode = (row.barcode or "").strip()
		if barcode:
			return barcode

	if doc.name:
		return (
			frappe.db.get_value(
				"Item Barcode",
				{"parent": doc.name, "barcode": ["!=", ""]},
				"barcode",
				order_by="idx asc",
			)
			or ""
		)

	return ""


def _has_barcode(doc):
	return any((row.barcode or "").strip() for row in doc.get(ITEM_BARCODE_PARENTFIELD, []))
