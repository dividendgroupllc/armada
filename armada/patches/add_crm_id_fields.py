"""Sales Order va Sales Invoice'ga CRM ID maydonini qo'shish.

Sales Order'da Delivery Date / Komment ustunining o'ng tomonidagi ustunda
(column_break1), "Customer's Purchase Order" tepasida turadi.
Sales Invoice'ga Sales Order'dan ko'chiriladi (events/sales_order.py).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CRM_ID_FIELD = "custom_crm_id"


def execute():
    # Avvalgi versiyadagi alohida ustun (4 ta ustun bo'lib qolardi)
    frappe.delete_doc_if_exists("Custom Field", "Sales Order-custom_crm_id_column")

    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": CRM_ID_FIELD,
                    "label": "ID",
                    "fieldtype": "Data",
                    "insert_after": "column_break1",
                    "in_standard_filter": 1,
                    "search_index": 1,
                },
            ],
            "Sales Invoice": [
                {
                    "fieldname": CRM_ID_FIELD,
                    "label": "ID",
                    "fieldtype": "Data",
                    "insert_after": "custom_komment",
                    "in_standard_filter": 1,
                    "search_index": 1,
                },
            ],
        }
    )
