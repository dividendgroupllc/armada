# Copyright (c) 2026, Armada and contributors
# For license information, please see license.txt

"""
Sotuv Hisoboti
==============
Sanama-sana: qaysi tovar, qancha, qaysi mijozga sotilgan va izoh (Komment).

Manba: Sales Invoice Item (docstatus = 1). Qaytarishlar (is_return) manfiy
miqdor bilan chiqadi.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.to_date:
		filters.to_date = today()
	if not filters.from_date:
		filters.from_date = add_months(filters.to_date, -1)
	if getdate(filters.from_date) > getdate(filters.to_date):
		filters.from_date, filters.to_date = filters.to_date, filters.from_date

	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Сана"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Ҳужжат"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
		{"label": _("Мижоз"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Товар номи"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Миқдор"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Нарх"), "fieldname": "rate", "fieldtype": "Currency", "options": "currency", "width": 100},
		{"label": _("Сумма"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Изоҳ"), "fieldname": "komment", "fieldtype": "Data", "width": 300},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]

	if filters.company:
		conditions.append("si.company = %(company)s")
	if filters.customer:
		conditions.append("si.customer = %(customer)s")
	if filters.item_code:
		conditions.append("sii.item_code = %(item_code)s")
	if filters.item_group:
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
		conditions.append(
			f"sii.item_group IN (SELECT name FROM `tabItem Group` WHERE lft >= {int(lft)} AND rgt <= {int(rgt)})"
		)
	if filters.warehouse:
		conditions.append("sii.warehouse = %(warehouse)s")
	if not filters.include_returns:
		conditions.append("si.is_return = 0")

	return frappe.db.sql(
		f"""
		SELECT
			si.posting_date,
			si.name AS invoice,
			si.customer,
			sii.item_name,
			sii.qty,
			sii.rate,
			sii.amount,
			si.custom_komment AS komment,
			si.currency
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY si.posting_date, si.posting_time, si.name, sii.idx
		""",
		filters,
		as_dict=True,
	)
