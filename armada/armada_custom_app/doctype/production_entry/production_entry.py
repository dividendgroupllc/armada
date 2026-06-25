# Copyright (c) 2025, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


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
        self.cancel_journal_entry()

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
        # "BOM Not Required" belgisi — Item kartochkasidan olinadi (yagona haqiqiy manba).
        if self.item_to_manufacture:
            self.bom_not_required = cint(
                frappe.db.get_value("Item", self.item_to_manufacture, "custom_no_bom_required")
            )

        # Belgilangan tovar uchun BOM ixtiyoriy — materiallar PE ichida qo'lda (dynamic)
        # kiritiladi yoki bo'sh qoldiriladi (masalan Услуга — xom-ashyosiz xizmat tovari).
        if self.bom_not_required:
            return

        if not self.bom_no:
            frappe.throw(_(
                "BOM No majburiy. Agar bu tovar BOM'siz ishlab chiqarilsa, "
                "Item kartochkasida 'BOM Not Required' ni yoqing."
            ))

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

    def _get_additional_cost_data(self):
        """Production Additional Cost dan item_to_manufacture uchun ma'lumot olish.
        Agar topilmasa None qaytaradi."""
        return frappe.db.get_value(
            "Production Additional Cost",
            {"item_code": self.item_to_manufacture},
            ["name", "amount", "expense_account", "description", "party_type", "party"],
            as_dict=True
        )

    def create_stock_entry(self):
        """Submit bo'lganda Stock Entry yaratish.

        Ikki holat:
          1) Xom-ashyo bilan (BOM yoki qo'lda) — "Manufacture":
             xom-ashyo + tayyor mahsulot, additional_costs jadvali bilan.
          2) Xom-ashyosiz (masalan Услуга) — "Material Receipt":
             ERPNext "Manufacture" uchun kamida bitta xom-ashyo talab qiladi, shuning uchun
             tayyor mahsulotni xizmat narxida to'g'ridan-to'g'ri kirim qilamiz. Buxgalteriya
             natijasi bir xil: Dr Ombor(FG) / Cr expense_account, keyin Journal Entry Cr party.
        """
        additional_cost = self._get_additional_cost_data()
        has_raw_materials = bool(self.items)
        total_additional = flt(additional_cost.amount) * flt(self.qty_to_manufacture) if additional_cost else 0

        se = frappe.new_doc("Stock Entry")
        se.posting_date = self.posting_date
        se.posting_time = self.posting_time
        se.set_posting_time = 1
        se.company = self.company
        se.custom_production_entry = self.name

        stock_uom = frappe.get_cached_value("Item", self.item_to_manufacture, "stock_uom")

        if has_raw_materials:
            se.stock_entry_type = "Manufacture"
            se.from_bom = 1 if self.bom_no else 0
            if self.bom_no:
                se.bom_no = self.bom_no
            se.fg_completed_qty = self.qty_to_manufacture

            # Xom-ashyo (source) qatorlari
            for item in self.items:
                se.append("items", {
                    "item_code": item.item_code,
                    "qty": item.required_qty,
                    "s_warehouse": item.source_warehouse,
                    "uom": item.uom or frappe.get_cached_value("Item", item.item_code, "stock_uom"),
                    "stock_uom": item.uom or frappe.get_cached_value("Item", item.item_code, "stock_uom"),
                    "conversion_factor": 1
                })

            # Tayyor mahsulot
            se.append("items", {
                "item_code": self.item_to_manufacture,
                "qty": self.qty_to_manufacture,
                "t_warehouse": self.target_warehouse,
                "is_finished_item": 1,
                "uom": stock_uom,
                "stock_uom": stock_uom,
                "conversion_factor": 1,
            })

            # Additional costs — narx tayyor mahsulotga taqsimlanadi
            if additional_cost:
                se.append("additional_costs", {
                    "expense_account": additional_cost.expense_account,
                    "description": additional_cost.description
                        or f"Production cost for {self.item_to_manufacture}",
                    "amount": total_additional,
                })
        else:
            # Xom-ashyosiz: tayyor mahsulotni xizmat narxida kirim qilamiz
            se.stock_entry_type = "Material Receipt"
            fg_row = {
                "item_code": self.item_to_manufacture,
                "qty": self.qty_to_manufacture,
                "t_warehouse": self.target_warehouse,
                "uom": stock_uom,
                "stock_uom": stock_uom,
                "conversion_factor": 1,
            }
            if additional_cost:
                # Narx = xizmat haqi; offset expense_account ga (keyin JE party'ga o'tkazadi)
                fg_row["basic_rate"] = flt(additional_cost.amount)
                fg_row["expense_account"] = additional_cost.expense_account
            else:
                # Narx manbasi yo'q — submit xatosini oldini olish uchun 0 valuation'ga ruxsat
                fg_row["allow_zero_valuation_rate"] = 1
            se.append("items", fg_row)

        se.flags.ignore_permissions = True
        se.insert()
        se.submit()

        # Save reference
        self.db_set("stock_entry", se.name)

        frappe.msgprint(_("Stock Entry {0} created").format(
            frappe.utils.get_link_to_form("Stock Entry", se.name)
        ))

        # Journal Entry — faqat additional cost mavjud bo'lsa
        if additional_cost:
            self.create_production_journal_entry(additional_cost, total_additional)

    def create_production_journal_entry(self, cost_data, total_amount):
        """Production additional cost uchun Journal Entry yaratish.

        Debit:  expense_account (masalan 5233 - Услуги)
        Credit: party account  (masalan 2110 - Creditors yoki 2120 - Payroll)
        """
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.posting_date
        je.company = self.company
        je.cheque_no = self.name
        je.cheque_date = self.posting_date
        je.user_remark = (
            f"Production cost for {self.item_to_manufacture} "
            f"(qty {self.qty_to_manufacture}) — {self.name}"
        )

        # Row 1 — Debit: expense account
        je.append("accounts", {
            "account": cost_data.expense_account,
            "debit_in_account_currency": total_amount,
            "debit": total_amount,
        })

        # Row 2 — Credit: party account
        party_account = self._get_party_account(cost_data.party_type)
        je.append("accounts", {
            "account": party_account,
            "credit_in_account_currency": total_amount,
            "credit": total_amount,
            "party_type": cost_data.party_type,
            "party": cost_data.party,
        })

        je.flags.ignore_permissions = True
        je.insert()
        je.submit()

        self.db_set("journal_entry", je.name)

        frappe.msgprint(_("Journal Entry {0} created").format(
            frappe.utils.get_link_to_form("Journal Entry", je.name)
        ))

    def _get_party_account(self, party_type):
        """Party type ga qarab creditor accountni olish.

        Supplier  → 2110
        Employee  → 2120
        """
        account_map = {
            "Supplier": "2110",
            "Employee": "2120",
        }
        account_number = account_map.get(party_type)
        if not account_number:
            frappe.throw(_("Unsupported party type: {0}").format(party_type))

        account = frappe.db.get_value(
            "Account",
            {"company": self.company, "account_number": account_number, "is_group": 0},
            "name"
        )
        if not account:
            frappe.throw(
                _("Account {0} not found for company {1}").format(account_number, self.company)
            )
        return account

    def cancel_journal_entry(self):
        """Bog'langan Journal Entry ni cancel qilish"""
        if not self.journal_entry:
            return

        je_docstatus = frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus")
        if je_docstatus == 1:
            try:
                je = frappe.get_doc("Journal Entry", self.journal_entry)
                je.flags.ignore_permissions = True
                je.cancel()
                frappe.msgprint(_("Journal Entry {0} cancelled").format(self.journal_entry))
            except Exception as e:
                frappe.throw(
                    _("Journal Entry {0} cancel bo'lmadi: {1}").format(
                        self.journal_entry, str(e)
                    )
                )

    def cancel_stock_entry(self):
        """Cancel ALL submitted Stock Entries linked to this Production Entry.

        Atomic: agar biror SE cancel bo'lmasa, frappe.throw qilib PE cancel'ni ham to'xtatadi.
        """
        linked = frappe.get_all(
            "Stock Entry",
            filters={"custom_production_entry": self.name, "docstatus": 1},
            pluck="name",
        )

        if self.stock_entry and self.stock_entry not in linked:
            if frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
                linked.append(self.stock_entry)

        for se_name in sorted(linked):
            try:
                se = frappe.get_doc("Stock Entry", se_name)
                se.flags.ignore_permissions = True
                se.ignore_linked_doctypes = ("Production Entry",)
                se.cancel()
                frappe.msgprint(_("Stock Entry {0} cancelled").format(se_name))
            except Exception as e:
                frappe.throw(
                    _("Stock Entry {0} bekor qilinmadi: {1}").format(se_name, str(e))
                )


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
def get_production_barcode_payload(production_entry):
	"""Return label data for QZ Tray barcode printing."""
	doc = frappe.get_doc("Production Entry", production_entry)
	doc.check_permission("read")

	if doc.docstatus != 1:
		frappe.throw(_("Barcode can only be printed after Production Entry is submitted"))

	qty = flt(doc.qty_to_manufacture)
	label_qty = cint(qty)
	if qty != label_qty:
		frappe.throw(_("Qty to Manufacture must be a whole number to print barcode labels"))

	if label_qty <= 0:
		frappe.throw(_("Qty to Manufacture must be greater than 0"))

	barcode = frappe.db.get_value(
		"Item Barcode",
		{"parent": doc.item_to_manufacture, "barcode": ["!=", ""]},
		"barcode",
		order_by="idx asc",
	)
	if not barcode:
		frappe.throw(_("Barcode not found for Item {0}").format(doc.item_to_manufacture))

	item = frappe.db.get_value(
		"Item",
		doc.item_to_manufacture,
		["item_name", "fp_type", "segment", "product_type", "standard"],
		as_dict=True,
	) or {}

	def label_value(value):
		return value or "None"

	return {
		"production_entry": doc.name,
		"stock_entry": doc.stock_entry,
		"item_code": doc.item_to_manufacture,
		"item_name": doc.item_name or item.get("item_name"),
		"barcode": barcode,
		"posting_date": label_value(doc.posting_date),
		"posting_time": label_value(doc.posting_time),
		"fp_type": label_value(item.get("fp_type")),
		"segment": label_value(item.get("segment")),
		"product_type": label_value(item.get("product_type")),
		"standard": label_value(item.get("standard")),
		"qty": label_qty,
	}


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
