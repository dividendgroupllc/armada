"""Manual e2e test for Production Entry cancel → Stock Entry cancel.

Run: bench --site <site> execute armada.armada_custom_app.doctype.production_entry.test_helper.run
"""

import frappe
from frappe.utils import today, nowtime

COMPANY = "Armada"
WAREHOUSE = "Stores - A"
TARGET_WH = "Finished Goods - A"
RAW_ITEM = "TEST-RAW-PE-001"
FG_ITEM = "TEST-FG-PE-001"


def _ensure_item(item_code):
    if not frappe.db.exists("Item", item_code):
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": 1,
        })
        item.insert(ignore_permissions=True)
        print(f"  Created Item {item_code}")


def _opening_stock(item_code, qty, warehouse):
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.posting_date = today()
    se.posting_time = nowtime()
    se.set_posting_time = 1
    se.company = COMPANY
    se.append("items", {
        "item_code": item_code,
        "qty": qty,
        "t_warehouse": warehouse,
        "basic_rate": 100,
    })
    se.flags.ignore_permissions = True
    se.insert()
    se.submit()
    print(f"  Opening stock SE: {se.name}")


def _ensure_bom(fg_item, raw_item):
    existing = frappe.db.get_value(
        "BOM", {"item": fg_item, "is_active": 1, "docstatus": 1}, "name"
    )
    if existing:
        print(f"  BOM exists: {existing}")
        return existing
    bom = frappe.new_doc("BOM")
    bom.item = fg_item
    bom.quantity = 1
    bom.is_active = 1
    bom.is_default = 1
    bom.company = COMPANY
    bom.append("items", {
        "item_code": raw_item,
        "qty": 2,
        "uom": "Nos",
        "rate": 100,
    })
    bom.flags.ignore_permissions = True
    bom.insert()
    bom.submit()
    print(f"  Created BOM: {bom.name}")
    return bom.name


def run():
    print("=== SETUP ===")
    _ensure_item(RAW_ITEM)
    _ensure_item(FG_ITEM)
    bom_no = _ensure_bom(FG_ITEM, RAW_ITEM)
    _opening_stock(RAW_ITEM, 100, WAREHOUSE)

    print("\n=== CREATE & SUBMIT PRODUCTION ENTRY ===")
    pe = frappe.new_doc("Production Entry")
    pe.posting_date = today()
    pe.posting_time = nowtime()
    pe.set_posting_time = 1
    pe.company = COMPANY
    pe.item_to_manufacture = FG_ITEM
    pe.bom_no = bom_no
    pe.qty_to_manufacture = 5
    pe.target_warehouse = TARGET_WH
    pe.append("items", {
        "item_code": RAW_ITEM,
        "source_warehouse": WAREHOUSE,
        "required_qty": 10,
        "uom": "Nos",
    })
    pe.flags.ignore_permissions = True
    pe.insert()
    pe.submit()
    pe.reload()
    print(f"  PE: {pe.name}, status={pe.status}, stock_entry={pe.stock_entry}")

    auto_se = pe.stock_entry
    assert auto_se, "Auto SE should be linked"
    assert frappe.db.get_value("Stock Entry", auto_se, "docstatus") == 1

    print("\n=== ADD EXTRA SE LINKED VIA custom_production_entry ===")
    extra_se = frappe.new_doc("Stock Entry")
    extra_se.stock_entry_type = "Material Issue"
    extra_se.posting_date = today()
    extra_se.posting_time = nowtime()
    extra_se.set_posting_time = 1
    extra_se.company = COMPANY
    extra_se.custom_production_entry = pe.name
    extra_se.append("items", {
        "item_code": RAW_ITEM,
        "qty": 1,
        "s_warehouse": WAREHOUSE,
    })
    extra_se.flags.ignore_permissions = True
    extra_se.insert()
    extra_se.submit()
    print(f"  Extra SE: {extra_se.name}")

    print("\n=== CANCEL PRODUCTION ENTRY ===")
    pe.reload()
    pe.flags.ignore_permissions = True
    pe.cancel()
    print(f"  PE cancelled: status={pe.status}, docstatus={pe.docstatus}")

    auto_after = frappe.db.get_value("Stock Entry", auto_se, "docstatus")
    extra_after = frappe.db.get_value("Stock Entry", extra_se.name, "docstatus")
    print(f"  Auto SE docstatus: {auto_after} (expected 2)")
    print(f"  Extra SE docstatus: {extra_after} (expected 2)")
    assert auto_after == 2, f"Auto SE should be cancelled, got {auto_after}"
    assert extra_after == 2, f"Extra SE should be cancelled, got {extra_after}"

    frappe.db.commit()
    print("\n=== ALL TESTS PASSED ===")
