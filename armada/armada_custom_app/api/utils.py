# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
Shared helper / utility functions for the Armada dashboard API modules.
These are low-level DB accessors used by main.py, sales.py, cashflow.py,
and counterparties.py.

All data is read from ERPNext standard doctypes:
  Sales Invoice, Purchase Invoice, Payment Entry, Journal Entry, Stock Entry
Only submitted documents (docstatus = 1) are considered.
"""

import frappe
from frappe.utils import flt, nowdate, get_first_day, add_months, getdate
from datetime import datetime
import calendar


# ── Smart date range ───────────────────────────────────────────────────────

def get_smart_date_range(from_date=None, to_date=None):
	"""Return a date range that actually has data.

	If from_date/to_date are provided explicitly by the user, use them as-is.
	If they are omitted (defaults), check whether the current month has any
	data in the three main doctypes (Sales Invoice, Payment Entry, Stock Entry).
	When the current month is empty, fall back to the most recent month that
	contains submitted data.
	"""
	if from_date and to_date:
		return str(from_date), str(to_date)

	# Default: current month (1st day to today)
	return str(get_first_day(nowdate())), str(nowdate())


# ── Percentage helpers ──────────────────────────────────────────────────────

def calculate_change(current, previous):
	"""Return percentage change between two values."""
	if not previous or previous == 0:
		return 0
	return ((current - previous) / abs(previous)) * 100


def calculate_profitability(sales, cost):
	"""Return profit margin percentage."""
	if not sales or sales == 0:
		return 0
	return ((sales - cost) / sales) * 100


# ── Sales (Sales Invoice) ──────────────────────────────────────────────────

def get_total_sales(from_date, to_date):
	"""Total sales amount for a period from Sales Invoice."""
	result = frappe.db.sql("""
		SELECT SUM(grand_total) FROM `tabSales Invoice`
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_sales_summary(from_date, to_date):
	"""Sales qty + amount + cost for a period from Sales Invoice + Items."""
	result = frappe.db.sql("""
		SELECT
			SUM(sii.qty) AS qty,
			SUM(sii.amount) AS amount,
			SUM(IFNULL(sii.incoming_rate, 0) * sii.qty) AS cost
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)

	if result and result[0]:
		return {
			"qty": flt(result[0].qty, 0),
			"amount": flt(result[0].amount, 2),
			"cost": flt(result[0].cost, 2),
		}
	return {"qty": 0, "amount": 0, "cost": 0}


# ── Purchases (Purchase Invoice) ───────────────────────────────────────────

def get_purchases_summary(from_date, to_date):
	"""Purchase qty + amount for a period from Purchase Invoice + Items."""
	result = frappe.db.sql("""
		SELECT
			SUM(pii.qty) AS qty,
			SUM(pii.amount) AS amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)

	# Raw materials — items whose item_group contains 'Сырьё' or 'Raw Material'
	raw_result = frappe.db.sql("""
		SELECT SUM(pii.amount)
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		LEFT JOIN `tabItem` item ON item.name = pii.item_code
		WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %s AND %s
			AND (item.item_group LIKE '%%Сырьё%%' OR item.item_group LIKE '%%Raw Material%%')
	""", (from_date, to_date))

	if result and result[0]:
		return {
			"qty": flt(result[0].qty, 0),
			"amount": flt(result[0].amount, 2),
			"raw_materials": flt(raw_result[0][0], 2) if raw_result and raw_result[0][0] else 0,
		}
	return {"qty": 0, "amount": 0, "raw_materials": 0}


# ── Cash Flow — Payment Entry ──────────────────────────────────────────────

def get_cash_flow_income(from_date, to_date):
	"""Total income (Receive) for a period from Payment Entry."""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive'
			AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_flow_expense(from_date, to_date):
	"""Total expense (Pay) for a period from Payment Entry."""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay'
			AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_income_by_method(from_date, to_date, payment_method):
	"""Income filtered by mode of payment from Payment Entry."""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive'
			AND mode_of_payment = %s
			AND posting_date BETWEEN %s AND %s
	""", (payment_method, from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_expense_by_method(from_date, to_date, payment_method):
	"""Expense filtered by mode of payment from Payment Entry."""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay'
			AND mode_of_payment = %s
			AND posting_date BETWEEN %s AND %s
	""", (payment_method, from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


# ── Dynamic Debt Calculation (uses cache from counterparties.py) ────────────

def get_customer_outstanding():
	"""Total customer outstanding — reads from counterparty cache."""
	from armada.armada_custom_app.api.counterparties import _get_customer_debts_cached
	data = _get_customer_debts_cached()
	return flt(sum(flt(r["amount"]) for r in data), 2)


def get_supplier_outstanding():
	"""Total supplier outstanding — reads from counterparty cache."""
	from armada.armada_custom_app.api.counterparties import _get_supplier_debts_cached
	data = _get_supplier_debts_cached()
	return flt(sum(flt(r["amount"]) for r in data), 2)


# ── Current Assets / Liabilities from GL Entry ─────────────────────────────

def get_current_assets():
	"""Sum of GL Entry balances (debit - credit) for all accounts under
	the Current Assets parent group, using the Account tree (lft/rgt)."""
	parent = frappe.db.get_value(
		"Account",
		{"name": "1100-1600 - Current Assets - AM"},
		["lft", "rgt"],
		as_dict=True,
	)
	if not parent:
		return 0

	result = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
			AND acc.lft >= %s AND acc.rgt <= %s
			AND acc.is_group = 0
	""", (parent.lft, parent.rgt))

	return flt(result[0][0], 2) if result and result[0][0] else 0


def get_current_liabilities():
	"""Sum of GL Entry balances (credit - debit) for all accounts under
	the Current Liabilities parent group, using the Account tree (lft/rgt)."""
	parent = frappe.db.get_value(
		"Account",
		{"name": "2100-2400 - Current Liabilities - AM"},
		["lft", "rgt"],
		as_dict=True,
	)
	if not parent:
		return 0

	result = frappe.db.sql("""
		SELECT SUM(gle.credit - gle.debit)
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
			AND acc.lft >= %s AND acc.rgt <= %s
			AND acc.is_group = 0
	""", (parent.lft, parent.rgt))

	return flt(result[0][0], 2) if result and result[0][0] else 0


# ── Cash / Transfer balances ────────────────────────────────────────────────

def get_cash_balance():
	"""Net cash balance (Наличные income − expense) from Payment Entry."""
	income = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive'
			AND mode_of_payment = 'Наличные'
	""")
	expense = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay'
			AND mode_of_payment = 'Наличные'
	""")

	return (flt(income[0][0]) if income and income[0][0] else 0) \
		 - (flt(expense[0][0]) if expense and expense[0][0] else 0)


def get_transfer_balance():
	"""Net transfer balance (Клик + Перечисление income − expense)."""
	income = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive'
			AND mode_of_payment IN ('Клик', 'Перечисление')
	""")
	expense = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay'
			AND mode_of_payment IN ('Клик', 'Перечисление')
	""")

	return (flt(income[0][0]) if income and income[0][0] else 0) \
		 - (flt(expense[0][0]) if expense and expense[0][0] else 0)
