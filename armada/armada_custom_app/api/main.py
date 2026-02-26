# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
ГЛАВНАЯ (Main Dashboard Page)
─────────────────────────────
All data from ERPNext standard doctypes:
  Sales Invoice — for sales totals
  Payment Entry — for cash flow income/expense
  Stock Entry (Manufacture), Work Order — for production data

KPI cards: Сумма продаж, Поступления от клиентов, Задолженность клиентов/поставщикам,
           Остаточная сумма кассы, Рабочий капитал
Charts:    Продажи за текущий год, Динамика оборота за текущий год
Table:     Произведено за текущий месяц
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, add_months, get_first_day, flt
from datetime import datetime
import calendar

from armada.armada_custom_app.api.utils import (
	calculate_change,
	get_total_sales,
	get_cash_flow_income,
	get_cash_flow_expense,
	get_customer_outstanding,
	get_supplier_outstanding,
	get_cash_balance,
	get_current_assets,
	get_current_liabilities,
	get_smart_date_range,
)


# ── KPI Cards ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_main_kpis(from_date=None, to_date=None):
	"""Main page KPI strip."""
	from_date, to_date = get_smart_date_range(from_date, to_date)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	total_sales = get_total_sales(from_date, to_date)
	prev_sales = get_total_sales(prev_from_date, prev_to_date)

	customer_receipts = get_cash_flow_income(from_date, to_date)
	prev_receipts = get_cash_flow_income(prev_from_date, prev_to_date)

	customer_debt = get_customer_outstanding(from_date, to_date)
	supplier_debt = get_supplier_outstanding(from_date, to_date)
	cash_balance = get_cash_balance()

	current_assets = get_current_assets()
	current_liabilities = get_current_liabilities()
	working_capital = current_assets - current_liabilities

	data = {
		"total_sales": total_sales,
		"sales_change": calculate_change(total_sales, prev_sales),
		"customer_receipts": customer_receipts,
		"receipts_change": calculate_change(customer_receipts, prev_receipts),
		"customer_debt": customer_debt,
		"supplier_debt": supplier_debt,
		"cash_balance": cash_balance,
		"working_capital": working_capital,
	}
	print(data)

	return data

# ── Продажи за текущий год (line chart) ─────────────────────────────────────

@frappe.whitelist()
def get_yearly_sales():
	"""Monthly sales totals for the current year."""
	year = datetime.now().year
	labels = []
	values = []

	month_names = [
		'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
		'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
	]

	for month in range(1, 13):
		from_date = f"{year}-{month:02d}-01"
		last_day = calendar.monthrange(year, month)[1]
		to_date = f"{year}-{month:02d}-{last_day}"

		labels.append(month_names[month - 1])
		values.append(flt(get_total_sales(from_date, to_date), 2))

	return {"labels": labels, "values": values}


# ── Динамика оборота за текущий год (bar chart) ─────────────────────────────

@frappe.whitelist()
def get_turnover_data():
	"""Monthly income/expense bars for the current year."""
	year = datetime.now().year
	labels = []
	income = []
	expense = []

	month_names_short = [
		'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
		'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек',
	]

	for month in range(1, 13):
		from_date = f"{year}-{month:02d}-01"
		last_day = calendar.monthrange(year, month)[1]
		to_date = f"{year}-{month:02d}-{last_day}"

		m_income = get_cash_flow_income(from_date, to_date)
		m_expense = get_cash_flow_expense(from_date, to_date)

		if m_income > 0 or m_expense > 0:
			labels.append(f"{month_names_short[month - 1]} {year}")
			income.append(flt(m_income, 2))
			expense.append(flt(m_expense, 2))

	return {"labels": labels, "income": income, "expense": expense}


# ── Произведено за текущий месяц (table) ────────────────────────────────────

@frappe.whitelist()
def get_production_data(from_date=None, to_date=None):
	"""Production output table — Stock Entry (Manufacture) or Work Order."""
	from_date, to_date = get_smart_date_range(from_date, to_date)

	# Try Stock Entry (Manufacture) first
	if frappe.db.exists("DocType", "Stock Entry"):
		try:
			data = frappe.db.sql("""
				SELECT se.posting_date AS date, sed.item_name, sed.uom,
					   SUM(sed.qty) AS qty
				FROM `tabStock Entry` se
				INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
				WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
					AND se.posting_date BETWEEN %s AND %s
					AND sed.is_finished_item = 1
				GROUP BY se.posting_date, sed.item_name, sed.uom
				ORDER BY se.posting_date DESC
			""", (from_date, to_date), as_dict=True)

			if data:
				return [{
					"date": r.date.strftime("%d.%m.%Y") if r.date else "",
					"item_name": r.item_name or "",
					"uom": r.uom or "ШТ",
					"qty": flt(r.qty, 0),
				} for r in data]
		except Exception:
			pass

	# Fallback: Work Order
	if frappe.db.exists("DocType", "Work Order"):
		try:
			data = frappe.db.sql("""
				SELECT wo.planned_start_date AS date, wo.item_name,
					   wo.stock_uom AS uom, wo.produced_qty AS qty
				FROM `tabWork Order` wo
				WHERE wo.docstatus = 1
					AND wo.planned_start_date BETWEEN %s AND %s
					AND wo.produced_qty > 0
				ORDER BY wo.planned_start_date DESC
			""", (from_date, to_date), as_dict=True)

			if data:
				return [{
					"date": r.date.strftime("%d.%m.%Y") if r.date else "",
					"item_name": r.item_name or "",
					"uom": r.uom or "ШТ",
					"qty": flt(r.qty, 0),
				} for r in data]
		except Exception:
			pass

	return []
