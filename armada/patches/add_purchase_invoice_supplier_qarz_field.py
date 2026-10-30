# Purchase Invoice'da supplier tanlanganda uning joriy qarzi ko'rsatiladi.
# Virtual maydon (bazada saqlanmaydi) — qiymatni
# armada/public/js/supplier_qarz.js to'ldiradi
# (server: armada.armada_custom_app.supplier_qarz.get_supplier_qarz).
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Invoice": [
				{
					"fieldname": "custom_supplier_qarz",
					"label": "Долг поставщику",
					"fieldtype": "Currency",
					# options yo'q: virtual maydonda options Python ifodasi sifatida
					# bajariladi. Valyuta — kompaniya standarti (USD).
					"options": "",
					"insert_after": "supplier_name",
					"is_virtual": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"depends_on": "eval:doc.supplier && doc.docstatus === 0",
					"description": "Musbat — biz qarzmiz, manfiy — supplier bizga qarz (avans).",
				},
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.clear_cache(doctype="Purchase Invoice")
