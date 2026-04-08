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
	return flt(((sales - cost) / sales) * 100, 2)


# ── Sales (Sales Invoice) ──────────────────────────────────────────────────

def get_total_sales(from_date, to_date):
	"""Total sales amount for a period from Sales Invoice."""
	result = frappe.db.sql("""
		SELECT SUM(grand_total) FROM `tabSales Invoice`
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_sales_summary(from_date, to_date):
	"""Sales qty from SI Items, amount from 4100 group, cost from 5111 (GL)."""
	qty_result = frappe.db.sql("""
		SELECT SUM(sii.qty)
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
	""", (from_date, to_date))
	qty = flt(qty_result[0][0], 0) if qty_result and qty_result[0][0] else 0

	income_parent = frappe.db.get_value(
		"Account",
		{"name": "4100 - Direct Income - AM"},
		["lft", "rgt"],
		as_dict=True,
	)

	amount = 0
	if income_parent:
		amount_result = frappe.db.sql("""
			SELECT SUM(gle.credit - gle.debit)
			FROM `tabGL Entry` gle
			INNER JOIN `tabAccount` acc ON acc.name = gle.account
			WHERE gle.is_cancelled = 0
				AND acc.is_group = 0
				AND acc.lft >= %s AND acc.rgt <= %s
				AND gle.posting_date BETWEEN %s AND %s
		""", (income_parent.lft, income_parent.rgt, from_date, to_date))
		amount = flt(amount_result[0][0], 2) if amount_result and amount_result[0][0] else 0

	cost_result = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
			AND gle.account = %s
			AND gle.posting_date BETWEEN %s AND %s
	""", ("5111 - Cost of Goods Sold - AM", from_date, to_date))
	cost = flt(cost_result[0][0], 2) if cost_result and cost_result[0][0] else 0

	return {
		"qty": qty,
		"amount": amount,
		"cost": cost,
	}


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
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Customer'
			AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_flow_supplier_income(from_date, to_date):
	"""Supplier inflow for period.

	Primary source: Payment Entry (Receive + Supplier).
	Fallback: submitted Purchase Invoices (incoming supplies) when direct receipts are absent.
	"""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Supplier'
			AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	direct_receipts = flt(result[0][0]) if result and result[0][0] else 0
	if direct_receipts > 0:
		return direct_receipts

	fallback = frappe.db.sql("""
		SELECT SUM(grand_total) FROM `tabPurchase Invoice`
		WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(fallback[0][0]) if fallback and fallback[0][0] else 0


def get_cash_flow_expense(from_date, to_date):
	"""Total expense (Pay) for a period from Payment Entry."""
	result = frappe.db.sql("""
		SELECT SUM(paid_amount) FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay'
			AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_income_by_method(from_date, to_date, payment_method):
	"""Income filtered by mode of payment from GL Entry (DDS-aligned)."""
	accounts = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": payment_method},
		fields=["default_account"],
		pluck="default_account"
	)
	accounts = list(set(a for a in accounts if a))
	if not accounts:
		return 0

	placeholders = ", ".join(["%s"] * len(accounts))
	result = frappe.db.sql("""
		SELECT IFNULL(SUM(debit_in_account_currency), 0)
		FROM `tabGL Entry`
		WHERE is_cancelled = 0
			AND account IN ({})
			AND posting_date BETWEEN %s AND %s
	""".format(placeholders), tuple(accounts) + (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


def get_cash_expense_by_method(from_date, to_date, payment_method):
	"""Expense filtered by mode of payment from GL Entry (DDS-aligned)."""
	accounts = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": payment_method},
		fields=["default_account"],
		pluck="default_account"
	)
	accounts = list(set(a for a in accounts if a))
	if not accounts:
		return 0

	placeholders = ", ".join(["%s"] * len(accounts))
	result = frappe.db.sql("""
		SELECT IFNULL(SUM(credit_in_account_currency), 0)
		FROM `tabGL Entry`
		WHERE is_cancelled = 0
			AND account IN ({})
			AND posting_date BETWEEN %s AND %s
	""".format(placeholders), tuple(accounts) + (from_date, to_date))

	return flt(result[0][0]) if result and result[0][0] else 0


# ── Dynamic Debt Calculation (uses cache from counterparties.py) ────────────

def get_customer_outstanding(from_date=None, to_date=None):
	"""Total customer outstanding — reads from counterparty cache or calculates for period."""
	if from_date and to_date:
		from armada.armada_custom_app.api.counterparties import _calc_customer_debts
		data = _calc_customer_debts(from_date, to_date)
		return flt(sum(flt(r["debt_amount"]) for r in data), 2)
	
	from armada.armada_custom_app.api.counterparties import _get_customer_debts_cached
	data = _get_customer_debts_cached()
	return flt(sum(flt(r["amount"]) for r in data), 2)


def get_supplier_outstanding(from_date=None, to_date=None):
	"""Total supplier outstanding — reads from counterparty cache or calculates for period."""
	if from_date and to_date:
		from armada.armada_custom_app.api.counterparties import _calc_supplier_debts
		data = _calc_supplier_debts(from_date, to_date)
		return flt(sum(flt(r["debt_amount"]) for r in data), 2)
		
	from armada.armada_custom_app.api.counterparties import _get_supplier_debts_cached
	data = _get_supplier_debts_cached()
	return flt(sum(flt(r["amount"]) for r in data), 2)


# ── Current Assets / Liabilities from GL Entry ─────────────────────────────

def get_current_assets():
	"""Sum of GL Entry balances (debit - credit) for all Asset accounts."""
	result = frappe.db.sql("""
		SELECT SUM(gle.debit - gle.credit)
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
			AND acc.root_type = 'Asset'
	""")

	return flt(result[0][0], 2) if result and result[0][0] else 0


def get_current_liabilities():
	"""Sum of GL Entry balances (credit - debit) for all Liability accounts."""
	result = frappe.db.sql("""
		SELECT SUM(gle.credit - gle.debit)
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
			AND acc.root_type = 'Liability'
	""")

	return flt(result[0][0], 2) if result and result[0][0] else 0


# ── Cash / Transfer balances ────────────────────────────────────────────────

def get_cash_balance(to_date=None):
    """Net cash balance from ALL Mode of Payment accounts from GL Entry."""
    from frappe.utils import flt
    import frappe

    accounts = frappe.get_all(
        "Mode of Payment Account",
        fields=["default_account"],
        pluck="default_account"
    )
    cash_accounts = list(set(a for a in accounts if a))

    if not cash_accounts:
        return 0.0

    placeholders = ", ".join(["%s"] * len(cash_accounts))
    date_condition = "AND posting_date <= %s" if to_date else ""
    params = tuple(cash_accounts)
    if to_date:
        params = params + (to_date,)

    query = f"""
        SELECT IFNULL(SUM(debit_in_account_currency) - SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE account IN ({placeholders})
          AND is_cancelled = 0
          {date_condition}
    """
    result = frappe.db.sql(query, params)

    return flt(result[0][0]) if result else 0.0



def get_transfer_balance(to_date=None):
	"""Net transfer balance (Клик + Перечисление income − expense) from GL Entry."""
	from frappe.utils import flt
	import frappe

	accounts = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": ["in", ["Клик", "Перечисление"]]},
		fields=["default_account"],
		pluck="default_account"
	)
	cash_accounts = list(set(a for a in accounts if a))

	if not cash_accounts:
		return 0.0

	placeholders = ", ".join(["%s"] * len(cash_accounts))
	date_condition = "AND posting_date <= %s" if to_date else ""
	params = tuple(cash_accounts)
	if to_date:
		params = params + (to_date,)

	query = f"""
		SELECT IFNULL(SUM(debit_in_account_currency) - SUM(credit_in_account_currency), 0)
		FROM `tabGL Entry`
		WHERE account IN ({placeholders})
		  AND is_cancelled = 0
		  {date_condition}
	"""
	result = frappe.db.sql(query, params)

	return flt(result[0][0]) if result else 0.0


def get_cash_balance_by_method(to_date=None, payment_method=None):
	"""Net cash balance for a specific Mode of Payment from GL Entry."""
	from frappe.utils import flt
	import frappe

	filters = {}
	if payment_method:
		filters["parent"] = payment_method

	accounts = frappe.get_all(
		"Mode of Payment Account",
		filters=filters,
		fields=["default_account"],
		pluck="default_account"
	)
	cash_accounts = list(set(a for a in accounts if a))

	if not cash_accounts:
		return 0.0

	placeholders = ", ".join(["%s"] * len(cash_accounts))
	date_condition = "AND posting_date <= %s" if to_date else ""
	params = tuple(cash_accounts)
	if to_date:
		params = params + (to_date,)

	query = f"""
		SELECT IFNULL(SUM(debit_in_account_currency) - SUM(credit_in_account_currency), 0)
		FROM `tabGL Entry`
		WHERE account IN ({placeholders})
		  AND is_cancelled = 0
		  {date_condition}
	"""
	result = frappe.db.sql(query, params)

	return flt(result[0][0]) if result else 0.0
