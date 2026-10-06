# Copyright (c) 2026, Armada and contributors
# For license information, please see license.txt

"""
Instagram Mijozlar Hisoboti
===========================
Customer Group = "Инстаграм" mijozlari kesimida: nechta tovar sotilgan, qanday
tovarlar, qancha puli tushgan va qancha qarz qolgan.

- Sotuv: Sales Invoice Item (docstatus = 1), qaytarishlar manfiy bo'lib ayiriladi.
- To'langan: davr ichidagi Payment Entry (GL Entry, party_type = Customer).
  To'lovlar odatda aniq invoysga bog'lanmaydi, shuning uchun Sales Invoice'ning
  outstanding_amount'i ishonchsiz — qarz GL bo'yicha mijoz balansidan olinadi.
- Qarz: "Охирги сана"гача бўлган мижоз балансы (debit - credit), davrdan oldingi
  qoldiq ham kiradi.

Natija daraxt ko'rinishida: mijoz qatori -> uning tovarlari.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

DEFAULT_GROUP = "Инстаграм"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.to_date:
		filters.to_date = today()
	if not filters.from_date:
		filters.from_date = add_months(filters.to_date, -1)
	if getdate(filters.from_date) > getdate(filters.to_date):
		filters.from_date, filters.to_date = filters.to_date, filters.from_date
	filters.customer_group = filters.customer_group or DEFAULT_GROUP

	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Мижоз / Товар"), "fieldname": "name", "fieldtype": "Data", "width": 260},
		{"label": _("Миқдор"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Сотилди"), "fieldname": "sold", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Тўланди"), "fieldname": "paid", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Қарз"), "fieldname": "debt", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Тўлов %"), "fieldname": "paid_pct", "fieldtype": "Percent", "width": 80},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	customers = frappe.get_all(
		"Customer",
		filters={"customer_group": filters.customer_group, **({"name": filters.customer} if filters.customer else {})},
		pluck="name",
	)
	if not customers:
		return []
	filters.customers = tuple(customers)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency") if filters.company else None

	item_conditions = [
		"si.docstatus = 1",
		"si.customer IN %(customers)s",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	if filters.company:
		item_conditions.append("si.company = %(company)s")
	if filters.item_group:
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
		item_conditions.append(
			f"sii.item_group IN (SELECT name FROM `tabItem Group` WHERE lft >= {int(lft)} AND rgt <= {int(rgt)})"
		)
	if not filters.include_returns:
		item_conditions.append("si.is_return = 0")

	items = frappe.db.sql(
		f"""
		SELECT si.customer, sii.item_code, sii.item_name,
			SUM(sii.qty) AS qty, SUM(sii.base_net_amount) AS sold
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {" AND ".join(item_conditions)}
		GROUP BY si.customer, sii.item_code, sii.item_name
		ORDER BY si.customer, sold DESC
		""",
		filters,
		as_dict=True,
	)

	gl_company = "AND company = %(company)s" if filters.company else ""
	paid = dict(
		frappe.db.sql(
			f"""
			SELECT party, SUM(credit - debit)
			FROM `tabGL Entry`
			WHERE is_cancelled = 0 AND party_type = 'Customer' AND party IN %(customers)s
				AND voucher_type = 'Payment Entry'
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_company}
			GROUP BY party
			""",
			filters,
		)
	)
	debt = dict(
		frappe.db.sql(
			f"""
			SELECT party, SUM(debit - credit)
			FROM `tabGL Entry`
			WHERE is_cancelled = 0 AND party_type = 'Customer' AND party IN %(customers)s
				AND posting_date <= %(to_date)s {gl_company}
			GROUP BY party
			""",
			filters,
		)
	)

	by_customer = {}
	for row in items:
		by_customer.setdefault(row.customer, []).append(row)

	data = []
	total = frappe._dict(qty=0, sold=0, paid=0, debt=0)
	# Davrda harakati bor yoki qarzi bor mijozlar
	for customer in sorted(customers):
		rows = by_customer.get(customer, [])
		c_paid, c_debt = paid.get(customer) or 0, debt.get(customer) or 0
		if not rows and not c_paid and not c_debt:
			continue
		qty = sum(r.qty for r in rows)
		sold = sum(r.sold for r in rows)
		data.append(
			{
				"name": customer,
				"parent_row": None,
				"indent": 0,
				"qty": qty,
				"sold": sold,
				"paid": c_paid,
				"debt": c_debt,
				"paid_pct": (c_paid / sold * 100) if sold > 0 else 0,
				"currency": currency,
				"bold": 1,
			}
		)
		for r in rows:
			data.append(
				{
					"name": f"{customer}::{r.item_code}",
					"label": r.item_name,
					"parent_row": customer,
					"indent": 1,
					"qty": r.qty,
					"sold": r.sold,
					"currency": currency,
				}
			)
		total.qty += qty
		total.sold += sold
		total.paid += c_paid
		total.debt += c_debt

	if data:
		data.append(
			{
				"name": _("Жами"),
				"parent_row": None,
				"indent": 0,
				"qty": total.qty,
				"sold": total.sold,
				"paid": total.paid,
				"debt": total.debt,
				"paid_pct": (total.paid / total.sold * 100) if total.sold > 0 else 0,
				"currency": currency,
				"bold": 1,
			}
		)
	return data
