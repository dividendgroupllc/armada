# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
P&L page — faqat "Готовый продукт" item group
─────────────────────────────────────────────
Profit and Loss report'ning item'ga bog'liq qatorlari, oyma-oy:

  4110 - Sales               = Sales Invoice Item.base_net_amount
  5111 - Cost of Goods Sold  = Stock Ledger Entry (Sales Invoice / Delivery Note)
                               -stock_value_difference

Ikkalasi ham posting_date bo'yicha — P&L report bilan bir xil (butun kompaniya
bo'yicha GL 4110 / 5111 bilan tekshirilgan). Qaytarishlar manfiy bo'lib ayiriladi.
"""

import frappe
from frappe.utils import flt, getdate

from armada.armada_custom_app.api.utils import get_smart_date_range

FINISHED_GOODS_GROUP = "Готовый продукт"

MONTH_NAMES = [
	'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
	'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]


def _params(from_date, to_date):
	return {"from_date": from_date, "to_date": to_date, "item_group": FINISHED_GOODS_GROUP}


def _revenue_by_month(from_date, to_date):
	rows = frappe.db.sql("""
		SELECT DATE_FORMAT(si.posting_date, '%%Y-%%m') AS ym, SUM(sii.base_net_amount) AS amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		INNER JOIN `tabItem` it ON it.name = sii.item_code
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND it.item_group = %(item_group)s
		GROUP BY ym
	""", _params(from_date, to_date), as_dict=True)
	return {r.ym: flt(r.amount, 2) for r in rows}


def _cogs_by_month(from_date, to_date):
	rows = frappe.db.sql("""
		SELECT DATE_FORMAT(sle.posting_date, '%%Y-%%m') AS ym, SUM(-sle.stock_value_difference) AS amount
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` it ON it.name = sle.item_code
		WHERE sle.is_cancelled = 0
			AND sle.voucher_type IN ('Sales Invoice', 'Delivery Note')
			AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND it.item_group = %(item_group)s
		GROUP BY ym
	""", _params(from_date, to_date), as_dict=True)
	return {r.ym: flt(r.amount, 2) for r in rows}


def _months_in_range(from_date, to_date):
	d, end = getdate(from_date).replace(day=1), getdate(to_date)
	months = []
	while d <= end:
		months.append((f"{d.year}-{d.month:02d}", f"{MONTH_NAMES[d.month - 1]} {d.year}"))
		d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
	return months


@frappe.whitelist()
def get_pl(from_date=None, to_date=None):
	"""P&L (Готовый продукт): oylar ustunlarda, qatorlar — P&L akkauntlari."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	revenue = _revenue_by_month(from_date, to_date)
	cogs = _cogs_by_month(from_date, to_date)

	columns = []
	for ym, label in _months_in_range(from_date, to_date):
		income, expense = revenue.get(ym, 0), cogs.get(ym, 0)
		columns.append({
			"label": label,
			"income": income,
			"expense": expense,
			"profit": flt(income - expense, 2),
		})

	return {"from_date": from_date, "to_date": to_date, "columns": columns}
