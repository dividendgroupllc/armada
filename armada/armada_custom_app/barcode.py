import frappe
from frappe.utils import nowdate, nowtime
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


@frappe.whitelist()
def get_item_primary_barcode(item_code):
	if not item_code:
		return ""

	return (
		frappe.db.get_value(
			"Item Barcode",
			{"parent": item_code, "barcode": ["!=", ""]},
			"barcode",
			order_by="idx asc",
		)
		or ""
	)


@frappe.whitelist()
def get_stock_entry_barcode_item_details(
	item_code,
	barcode=None,
	company=None,
	purpose=None,
	warehouse=None,
	qty=1,
	posting_date=None,
	posting_time=None,
):
	if not item_code:
		frappe.throw("Item Code is required.")

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.company = company or frappe.defaults.get_user_default("Company")
	stock_entry.purpose = purpose or "Material Receipt"
	stock_entry.posting_date = posting_date or nowdate()
	stock_entry.posting_time = posting_time or nowtime()

	details = stock_entry.get_item_details(
		{
			"item_code": item_code,
			"warehouse": warehouse or "",
			"qty": qty or 1,
			"transfer_qty": qty or 1,
			"company": stock_entry.company,
			"voucher_type": "Stock Entry",
			"voucher_no": "",
			"allow_zero_valuation": 1,
		}
	)
	details.item_code = item_code
	details.barcode = barcode or get_item_primary_barcode(item_code)
	details.qty = details.qty or qty or 1
	details.transfer_qty = details.transfer_qty or details.qty

	return details


def _has_barcode(doc):
	return any((row.barcode or "").strip() for row in doc.get(ITEM_BARCODE_PARENTFIELD, []))
