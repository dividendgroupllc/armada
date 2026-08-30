# Hujjat qatorida ombor qoldig'i (hujjat sanasi-soati bo'yicha) ko'rsatiladi.
# Qiymatni armada/public/js/ombor_qoldiq.js to'ldiradi
# (server: armada.armada_custom_app.ombor_qoldiq.get_qoldiqlar).
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELD = {
	"fieldname": "custom_ombor_qoldiq",
	"label": "Остаток на дату",
	"fieldtype": "Float",
	"read_only": 1,
	"no_copy": 1,
	"print_hide": 1,
	"allow_on_submit": 0,
	"in_list_view": 1,
	"columns": 1,
}

TARGETS = {
	"Purchase Receipt Item": "warehouse",
	"Purchase Invoice Item": "warehouse",
	"Delivery Note Item": "warehouse",
	"Sales Invoice Item": "warehouse",
	"Stock Entry Detail": "qty",
}


def execute():
	create_custom_fields(
		{
			doctype: [dict(FIELD, insert_after=insert_after)]
			for doctype, insert_after in TARGETS.items()
		},
		ignore_validate=True,
		update=True,
	)

	for doctype in TARGETS:
		frappe.clear_cache(doctype=doctype)
