# Hujjat qatorlari uchun ombor qoldig'ini hujjat sanasi-soati bo'yicha qaytaradi.
# ERPNext'ning o'z get_stock_balance funksiyasidan foydalanadi (Stock Ledger
# bo'yicha o'sha paytdagi qty_after_transaction).
import json

import frappe
from frappe.utils import flt

from erpnext.stock.utils import get_stock_balance


@frappe.whitelist()
def get_qoldiqlar(items, posting_date=None, posting_time=None):
	"""items: [{"name": row_name, "item_code": ..., "warehouse": ...}, ...]
	-> {row_name: qoldiq}"""
	if isinstance(items, str):
		items = json.loads(items)

	result = {}
	cache = {}
	for row in items:
		item_code = row.get("item_code")
		warehouse = row.get("warehouse")
		if not (row.get("name") and item_code and warehouse):
			continue

		key = (item_code, warehouse)
		if key not in cache:
			cache[key] = flt(
				get_stock_balance(item_code, warehouse, posting_date, posting_time)
			)
		result[row["name"]] = cache[key]

	return result
