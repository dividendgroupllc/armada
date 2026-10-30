# Supplier'ning joriy qarzi (barcha hisoblar bo'yicha: 2110 Creditors,
# 1312 avanslar va h.k.) — kompaniya valyutasida.
# GL'da debit - credit; supplier uchun teskarisi = biz qancha qarzmiz.
import frappe
from frappe.utils import flt

from erpnext.accounts.utils import get_balance_on


@frappe.whitelist()
def get_supplier_qarz(supplier, company):
	frappe.has_permission("Supplier", "read", supplier, throw=True)
	balance = get_balance_on(
		party_type="Supplier",
		party=supplier,
		company=company,
		in_account_currency=False,
	)
	return -flt(balance)
