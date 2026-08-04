"""Production Entry'ga zakaz (Sales Order) bog'lanish maydonlarini qo'shish."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from armada.armada_custom_app.events.production_from_sales_order import (
    CUSTOMER_FIELD,
    DUE_FIELD,
    SO_FIELD,
    SO_ITEM_FIELD,
    SOURCE_FIELD,
    SOURCE_MANUAL,
    SOURCE_SALES_ORDER,
)


def execute():
    create_custom_fields(
        {
            "Production Entry": [
                {
                    "fieldname": SOURCE_FIELD,
                    "label": "Manba",
                    "fieldtype": "Select",
                    "options": f"{SOURCE_MANUAL}\n{SOURCE_SALES_ORDER}",
                    "default": SOURCE_MANUAL,
                    "insert_after": "status",
                    "read_only": 1,
                    "in_standard_filter": 1,
                    "in_list_view": 1,
                },
                {
                    "fieldname": "custom_zakaz_section",
                    "label": "Zakaz ma'lumotlari",
                    "fieldtype": "Section Break",
                    "insert_after": "target_warehouse",
                    "depends_on": f"eval:doc.{SOURCE_FIELD}=='{SOURCE_SALES_ORDER}'",
                },
                {
                    "fieldname": SO_FIELD,
                    "label": "Zakaz",
                    "fieldtype": "Link",
                    "options": "Sales Order",
                    "insert_after": "custom_zakaz_section",
                    "read_only": 1,
                    "in_standard_filter": 1,
                },
                {
                    "fieldname": CUSTOMER_FIELD,
                    "label": "Mijoz",
                    "fieldtype": "Data",
                    "insert_after": SO_FIELD,
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_zakaz_column",
                    "fieldtype": "Column Break",
                    "insert_after": CUSTOMER_FIELD,
                },
                {
                    "fieldname": DUE_FIELD,
                    "label": "Yetkazish muddati",
                    "fieldtype": "Date",
                    "insert_after": "custom_zakaz_column",
                    "read_only": 1,
                    "in_list_view": 1,
                },
                {
                    "fieldname": SO_ITEM_FIELD,
                    "label": "Sales Order Item",
                    "fieldtype": "Data",
                    "insert_after": DUE_FIELD,
                    "read_only": 1,
                    "hidden": 1,
                    "no_copy": 1,
                },
            ]
        },
        ignore_validate=True,
    )

    # Mavjud 3400+ yozuv — hammasi qo'lda yaratilgan.
    frappe.db.sql(
        f"""
        UPDATE `tabProduction Entry`
        SET `{SOURCE_FIELD}` = %s
        WHERE IFNULL(`{SOURCE_FIELD}`, '') = ''
        """,
        SOURCE_MANUAL,
    )
