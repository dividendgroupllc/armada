"""
Move «Яндекс инстаграм» (5236) under the «Инстаграм» (5238) group account.

Both accounts already live under 52003 «Коммерческие», so the commercial
subtotal is unchanged — only the tree nesting changes. After this patch the
standard Profit and Loss Statement shows 5236 nested inside the 5238 group
(alongside 5239 «Таргет»), and the custom P&L PDF draws it as a leaf of the
Instagram group.

Idempotent: re-running is a no-op once 5236's parent is already 5238.
"""
import frappe

CHILD_NUMBER  = "5236"   # Яндекс инстаграм
PARENT_NUMBER = "5238"   # Инстаграм (group)


def execute():
    children = frappe.get_all(
        "Account",
        filters={"account_number": CHILD_NUMBER},
        fields=["name", "parent_account", "company"],
    )
    for acc in children:
        parent = frappe.db.get_value(
            "Account",
            {"account_number": PARENT_NUMBER, "company": acc.company, "is_group": 1},
            "name",
        )
        if not parent or acc.parent_account == parent:
            continue

        doc = frappe.get_doc("Account", acc.name)
        doc.parent_account = parent
        doc.flags.ignore_permissions = True
        doc.save()

    frappe.db.commit()
