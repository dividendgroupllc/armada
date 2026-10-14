"""Sales Order'ga "Hudud" maydonini qo'shish: sotuv Toshkentga yoki Viloyatga.

Select (radiobutton o'rniga) — faqat bittasini tanlash mumkin. Ixtiyoriy:
ayrim zakazlarda hudud tanlanmaydi.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

HUDUD_FIELD = "custom_hudud"


def execute():
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": HUDUD_FIELD,
                    "label": "Hudud",
                    "fieldtype": "Select",
                    "options": "\nToshkent\nViloyat",
                    "insert_after": "order_type",
                    "reqd": 0,
                    "mandatory_depends_on": "",
                    "in_standard_filter": 1,
                    "in_list_view": 1,
                },
            ],
        }
    )
