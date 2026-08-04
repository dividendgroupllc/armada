"""Ishlab chiqarish menedjeri zakaz navbatini ko'ra olishi uchun sozlamalar.

1. `Ishlab chiqarish menedjeri` roliga Sales Order'ni o'qish huquqi (hozir umuman yo'q).
2. Workspace'ga "Zakazdan kelgan ishlab chiqarish" shortcut'i.
"""

import json

import frappe

from armada.armada_custom_app.events.production_from_sales_order import (
    SOURCE_FIELD,
    SOURCE_SALES_ORDER,
)

ROLE = "Ishlab chiqarish menedjeri"
WORKSPACE = "Ishlab chiqarish menedjeri"
SHORTCUT_LABEL = "Zakazdan kelgan ishlab chiqarish"


def execute():
    _grant_sales_order_read()
    _add_workspace_shortcut()


def _grant_sales_order_read():
    if not frappe.db.exists("Role", ROLE):
        return

    if frappe.db.exists("Custom DocPerm", {"parent": "Sales Order", "role": ROLE, "permlevel": 0}):
        return

    frappe.get_doc(
        {
            "doctype": "Custom DocPerm",
            "parent": "Sales Order",
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": ROLE,
            "permlevel": 0,
            "read": 1,
            "report": 1,
            "select": 1,
        }
    ).insert(ignore_permissions=True)

    frappe.clear_cache(doctype="Sales Order")


def _add_workspace_shortcut():
    if not frappe.db.exists("Workspace", WORKSPACE):
        return

    workspace = frappe.get_doc("Workspace", WORKSPACE)
    if any(shortcut.label == SHORTCUT_LABEL for shortcut in workspace.shortcuts):
        return

    workspace.append(
        "shortcuts",
        {
            "type": "DocType",
            "label": SHORTCUT_LABEL,
            "link_to": "Production Entry",
            "color": "Orange",
            "stats_filter": json.dumps(
                {"docstatus": "0", SOURCE_FIELD: SOURCE_SALES_ORDER}
            ),
        },
    )
    workspace.save(ignore_permissions=True)
