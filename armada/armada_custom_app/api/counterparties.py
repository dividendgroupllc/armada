# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
КОНТРАГЕНТЫ (Counterparties Page)
──────────────────────────────────
Debt calculation uses ERPNext's GL Entry (General Ledger) — the
single source of truth for all accounting balances.  GL Entry
accounts for Sales/Purchase Invoices, Payment Entries, Credit Notes,
Journal Entries, and every other voucher that touches Receivable /
Payable accounts.

Results are cached in Redis and refreshed every 3 minutes
via the scheduler (see hooks.py → scheduler_events).

KPI cards: Задолженность клиентов, Количество клиентов,
           Задолженность поставщикам, Количество поставщиков
Tables:    Задолженность клиентов, Задолженность поставщикам
"""

import json
import frappe
from frappe import _
from frappe.utils import flt

# Cache keys
CACHE_KEY_SUPPLIER = "armada_supplier_debts"
CACHE_KEY_CUSTOMER = "armada_customer_debts"
CACHE_TTL = 300  # 5 minutes TTL (safety net if scheduler misses)


# ── Core calculation (GL Entry — ERPNext standard) ──────────────────────────

def _calc_supplier_debts(from_date=None, to_date=None):
	"""
	Calculate debt for each supplier from GL Entry.
	"""
	date_condition = ""
	params = []
	if to_date:
		date_condition = "AND gle.posting_date <= %s"
		params.append(to_date)
	elif from_date and not to_date:
		date_condition = "AND gle.posting_date <= %s"
		params.append(from_date)

	data = frappe.db.sql(f"""
		SELECT
			gle.party                          AS supplier,
			SUM(gle.credit - gle.debit) AS debt_amount
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled   = 0
			AND gle.party_type   = 'Supplier'
			AND gle.party IS NOT NULL AND gle.party != ''
			{date_condition}
		GROUP BY gle.party
	
HAVING debt_amount != 0
		ORDER BY debt_amount DESC
	""", tuple(params), as_dict=True)

	return data or []


def _calc_customer_debts(from_date=None, to_date=None):
	"""
	Calculate debt for each customer from GL Entry.
	"""
	date_condition = ""
	params = []
	if to_date:
		date_condition = "AND gle.posting_date <= %s"
		params.append(to_date)
	elif from_date and not to_date:
		date_condition = "AND gle.posting_date <= %s"
		params.append(from_date)

	data = frappe.db.sql(f"""
		SELECT
			gle.party                          AS customer,
			SUM(gle.debit - gle.credit) AS debt_amount
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled   = 0
			AND gle.party_type   = 'Customer'
			AND gle.party IS NOT NULL AND gle.party != ''
			{date_condition}
		GROUP BY gle.party

HAVING debt_amount != 0
		ORDER BY debt_amount DESC
	""", tuple(params), as_dict=True)

	return data or []



# ── Cache layer ─────────────────────────────────────────────────────────────

def _get_cached(key):
	"""Get cached data from Redis."""
	data = frappe.cache().get_value(key)
	if data:
		try:
			return json.loads(data)
		except (json.JSONDecodeError, TypeError):
			return None
	return None


def _set_cache(key, data):
	"""Store data in Redis with TTL."""
	frappe.cache().set_value(key, json.dumps(data, default=str), expires_in_sec=CACHE_TTL)


def _get_supplier_debts_cached():
	"""Get supplier debts from cache, or calculate and cache."""
	cached = _get_cached(CACHE_KEY_SUPPLIER)
	if cached is not None:
		return cached

	rows = _calc_supplier_debts()
	result = [{"supplier": r.supplier, "amount": flt(r.debt_amount, 2)} for r in rows]
	_set_cache(CACHE_KEY_SUPPLIER, result)
	return result


def _get_customer_debts_cached():
	"""Get customer debts from cache, or calculate and cache."""
	cached = _get_cached(CACHE_KEY_CUSTOMER)
	if cached is not None:
		return cached

	rows = _calc_customer_debts()
	result = [{"customer": r.customer, "amount": flt(r.debt_amount, 2)} for r in rows]
	_set_cache(CACHE_KEY_CUSTOMER, result)
	return result


# ── Scheduler task (called every 3 min from hooks.py) ───────────────────────

def refresh_counterparty_cache():
	"""
	Pre-calculate and cache counterparty debts.
	Called by Frappe scheduler every 3 minutes.
	"""
	try:
		supplier_rows = _calc_supplier_debts()
		supplier_data = [{"supplier": r.supplier, "amount": flt(r.debt_amount, 2)} for r in supplier_rows]
		_set_cache(CACHE_KEY_SUPPLIER, supplier_data)

		customer_rows = _calc_customer_debts()
		customer_data = [{"customer": r.customer, "amount": flt(r.debt_amount, 2)} for r in customer_rows]
		_set_cache(CACHE_KEY_CUSTOMER, customer_data)

		frappe.logger("armada").info(
			f"Counterparty cache refreshed: {len(supplier_data)} suppliers, {len(customer_data)} customers"
		)
	except Exception:
		frappe.log_error("Counterparty cache refresh failed")


# ── KPI Cards ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_counterparties_kpis():
	"""Counterparties page KPI strip — from cache."""
	supplier_data = _get_supplier_debts_cached()
	customer_data = _get_customer_debts_cached()

	supplier_debt = sum(flt(r["amount"]) for r in supplier_data)
	customer_debt = sum(flt(r["amount"]) for r in customer_data)

	return {
		"customer_debt": flt(customer_debt, 2),
		"customer_count": len(customer_data),
		"supplier_debt": flt(supplier_debt, 2),
		"supplier_count": len(supplier_data),
	}


# ── Задолженность клиентов (table) ──────────────────────────────────────────

@frappe.whitelist()
def get_customer_debts():
	"""Customer debts — from cache."""
	return _get_customer_debts_cached()


# ── Задолженность поставщикам (table) ────────────────────────────────────────

@frappe.whitelist()
def get_supplier_debts():
	"""Supplier debts — from cache."""
	return _get_supplier_debts_cached()
