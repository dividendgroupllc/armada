import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from armada.armada_custom_app.barcode import ITEM_BARCODE_DISPLAY_FIELD


def execute():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": ITEM_BARCODE_DISPLAY_FIELD,
					"label": "Barcode",
					"fieldtype": "Data",
					"insert_after": "item_name",
					"read_only": 1,
					"no_copy": 1,
					"in_global_search": 1,
				}
			]
		},
		ignore_validate=True,
	)

	barcode_rows = frappe.get_all(
		"Item Barcode",
		filters={"barcode": ["!=", ""]},
		fields=["parent", "barcode"],
		order_by="parent asc, idx asc",
	)

	seen = set()
	for row in barcode_rows:
		if row.parent in seen:
			continue

		seen.add(row.parent)
		frappe.db.set_value(
			"Item",
			row.parent,
			ITEM_BARCODE_DISPLAY_FIELD,
			row.barcode,
			update_modified=False,
		)
