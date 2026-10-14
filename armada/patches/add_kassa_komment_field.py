"""Sales Order'ga "Kassa Komment" maydonini qo'shish.

Sotuvchining Komment'idan alohida — kassa zakazni tasdiqlayotganda yozadi.
permlevel 2: faqat "kassa admin" ko'radi va yozadi, sotuvchi ko'rmaydi
(permlevel 1 standart ignore_pricing_rule bilan band, shuning uchun 2).
allow_on_submit: tasdiqlangandan keyin ham to'ldirish mumkin.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

KASSA_KOMMENT_FIELD = "custom_kassa_komment"
PERMLEVEL = 2
ROLE = "kassa admin"


def execute():
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": KASSA_KOMMENT_FIELD,
                    "label": "Kassa Komment",
                    "fieldtype": "Data",
                    "insert_after": "custom_komment",
                    "permlevel": PERMLEVEL,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                },
            ],
        }
    )

    if not frappe.db.exists("Role", ROLE):
        return
    add_permission("Sales Order", ROLE, PERMLEVEL)
    update_permission_property("Sales Order", ROLE, PERMLEVEL, "write", 1)
