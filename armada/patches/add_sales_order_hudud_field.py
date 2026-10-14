"""Sales Order'ga "Hudud" maydonini qo'shish: sotuv Toshkentga yoki Viloyatga.

Select (radiobutton o'rniga) — faqat bittasini tanlash mumkin.
Faqat qoralama (docstatus=0) uchun majburiy: reqd=1 bo'lsa, maydon bo'sh qolgan
eski tasdiqlangan zakazlarni (masalan Kassa Komment yozish uchun) saqlab bo'lmay qoladi.
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
                    "mandatory_depends_on": "eval:doc.docstatus==0",
                    "in_standard_filter": 1,
                    "in_list_view": 1,
                },
            ],
        }
    )
