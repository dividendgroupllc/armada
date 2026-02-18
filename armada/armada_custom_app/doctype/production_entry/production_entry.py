# Copyright (c) 2025, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProductionEntry(Document):
    def validate(self):
        self.set_status()
        self.validate_qty()
        self.validate_bom()
        self.update_available_qty()

    def on_submit(self):
        self.set_status("Submitted")
        self.db_set("status", "Submitted")
        self.create_stock_entry()

    def on_cancel(self):
        self.set_status("Cancelled")
        self.db_set("status", "Cancelled")
        self.cancel_stock_entry()

    def set_status(self, status=None):
        if status:
            self.status = status
        elif self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            self.status = "Submitted"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def validate_qty(self):
        if flt(self.qty_to_manufacture) <= 0:
            frappe.throw(_("Qty to Manufacture must be greater than 0"))

        for item in self.items:
            if flt(item.required_qty) <= 0:
                frappe.throw(_("Required Qty for {0} must be greater than 0").format(item.item_code))

    def validate_bom(self):
        if self.bom_no and self.item_to_manufacture:
            bom = frappe.get_doc("BOM", self.bom_no)
            if bom.item != self.item_to_manufacture:
                frappe.throw(_("BOM {0} is not for Item {1}").format(self.bom_no, self.item_to_manufacture))

    def update_available_qty(self):
        """Update available qty for all items based on posting date/time"""
        for item in self.items:
            if item.item_code and item.source_warehouse:
                item.available_qty = get_stock_balance(
                    item.item_code,
                    item.source_warehouse,
                    self.posting_date,
                    self.posting_time
                )

    def create_stock_entry(self):
        """Submit bo'lganda Stock Entry (Manufacture) yaratish"""
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Manufacture"
        se.posting_date = self.posting_date
        se.posting_time = self.posting_time
        se.set_posting_time = 1
        se.company = self.company
        se.from_bom = 1
        se.bom_no = self.bom_no
        se.fg_completed_qty = self.qty_to_manufacture
        se.custom_production_entry = self.name

        # Add raw materials (source items)
        for item in self.items:
            se.append("items", {
                "item_code": item.item_code,
                "qty": item.required_qty,
                "s_warehouse": item.source_warehouse,
                "uom": item.uom or frappe.get_cached_value("Item", item.item_code, "stock_uom"),
                "stock_uom": item.uom or frappe.get_cached_value("Item", item.item_code, "stock_uom"),
                "conversion_factor": 1
            })

        # Add finished good (target item)
        se.append("items", {
            "item_code": self.item_to_manufacture,
            "qty": self.qty_to_manufacture,
            "t_warehouse": self.target_warehouse,
            "is_finished_item": 1,
            "uom": frappe.get_cached_value("Item", self.item_to_manufacture, "stock_uom"),
            "stock_uom": frappe.get_cached_value("Item", self.item_to_manufacture, "stock_uom"),
            "conversion_factor": 1
        })

        se.flags.ignore_permissions = True
        se.insert()
        se.submit()

        # Save reference
        self.db_set("stock_entry", se.name)

        frappe.msgprint(_("Stock Entry {0} created").format(
            frappe.utils.get_link_to_form("Stock Entry", se.name)
        ))

    def cancel_stock_entry(self):
        """Cancel linked Stock Entry"""
        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.flags.ignore_permissions = True
                se.cancel()
                frappe.msgprint(_("Stock Entry {0} cancelled").format(self.stock_entry))


@frappe.whitelist()
def get_bom_for_item(item_code):
    """Item uchun default BOM olish"""
    if not item_code:
        return None

    bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_active": 1, "is_default": 1, "docstatus": 1},
        "name"
    )

    if not bom:
        # Default bo'lmasa, birinchi active BOM ni olish
        bom = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_active": 1, "docstatus": 1},
            "name",
            order_by="creation desc"
        )

    return bom


@frappe.whitelist()
def get_bom_items(bom_no, qty_to_manufacture, posting_date=None, posting_time=None, source_warehouse=None):
    """BOM dan materiallarni olish va required_qty ni hisoblash"""
    if not bom_no:
        return []

    bom = frappe.get_doc("BOM", bom_no)
    items = []

    default_warehouse = source_warehouse or ""

    for bom_item in bom.items:
        # Calculate required qty proportionally
        required_qty = flt(bom_item.qty) * flt(qty_to_manufacture) / flt(bom.quantity)

        warehouse = default_warehouse

        # Get available qty
        available_qty = get_stock_balance(
            bom_item.item_code,
            warehouse,
            posting_date,
            posting_time
        )

        items.append({
            "item_code": bom_item.item_code,
            "item_name": bom_item.item_name,
            "source_warehouse": warehouse,
            "required_qty": required_qty,
            "available_qty": available_qty,
            "uom": bom_item.stock_uom or bom_item.uom
        })

    return items


@frappe.whitelist()
def get_stock_balance(item_code, warehouse, posting_date=None, posting_time=None):
    """Ma'lum vaqtdagi stock balansni olish"""
    if not item_code or not warehouse:
        return 0

    if not posting_date:
        posting_date = frappe.utils.today()

    if not posting_time:
        posting_time = frappe.utils.nowtime()

    from erpnext.stock.utils import get_stock_balance as _get_stock_balance
    return flt(_get_stock_balance(item_code, warehouse, posting_date, posting_time))


@frappe.whitelist()
def get_available_qty_for_item(item_code, warehouse, posting_date=None, posting_time=None):
    """Single item uchun available qty olish (frontend uchun)"""
    return get_stock_balance(item_code, warehouse, posting_date, posting_time)
