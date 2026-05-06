# Copyright (c) 2025, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProductionAdditionalCost(Document):
    def validate(self):
        self.validate_amount()
        self.validate_unique_item()

    def validate_amount(self):
        if flt(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than 0"))

    def validate_unique_item(self):
        """Bitta item_code faqat bitta marta bo'lishi kerak"""
        existing = frappe.db.get_value(
            "Production Additional Cost",
            {"item_code": self.item_code, "name": ("!=", self.name)},
            "name"
        )
        if existing:
            frappe.throw(
                _("Item {0} already has additional cost entry: {1}").format(
                    self.item_code, existing
                )
            )
