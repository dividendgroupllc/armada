import frappe

from armada.armada_custom_app.barcode import generate_item_barcode


def execute():
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0},
		fields=["name", "stock_uom"],
		order_by="creation asc",
	)

	for item in items:
		if frappe.db.exists("Item Barcode", {"parent": item.name, "barcode": ["!=", ""]}):
			continue

		idx = (frappe.db.count("Item Barcode", {"parent": item.name}) or 0) + 1
		frappe.get_doc(
			{
				"doctype": "Item Barcode",
				"parent": item.name,
				"parenttype": "Item",
				"parentfield": "barcodes",
				"idx": idx,
				"barcode": generate_item_barcode(),
				"uom": item.stock_uom,
			}
		).insert(ignore_permissions=True)
