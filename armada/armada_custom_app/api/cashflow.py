# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
ДЕНЕЖНЫЙ ОБОРОТ (Cash Flow Page)
─────────────────────────────────
All data from ERPNext standard doctypes:
  Payment Entry — for income/expense cash flow
  Purchase Invoice, Journal Entry — for expense ranking fallback

Filters: payment_modes (Тип расчёта), categories (Список категорий = expense accounts),
         counterparties (Список контрагентов = party)

KPI cards: Наличный приход, Перечисление приход, Наличный расход,
           Перечисление расход, Текущий остаток наличные, Тек. остаток перечисление
Charts:    Динамика прихода и расхода (bar)
Tables:    Рейтинг приходов, Рейтинг расходов, Данные по обороту
"""

import json
import frappe
from frappe import _
from frappe.utils import getdate, nowdate, add_months, get_first_day, flt
from datetime import timedelta

from armada.armada_custom_app.api.utils import (
	calculate_change,
	get_cash_flow_income,
	get_cash_flow_expense,
	get_cash_income_by_method,
	get_cash_expense_by_method,
	get_cash_balance,
	get_transfer_balance,
	get_smart_date_range,
)


# ── Helpers for multi-select filters ────────────────────────────────────────

def _parse_json_list(val):
	"""Parse a JSON-encoded list sent from the frontend, or return empty list."""
	if not val:
		return []
	if isinstance(val, list):
		return val
	try:
		parsed = json.loads(val)
		if isinstance(parsed, list):
			return [v for v in parsed if v]
		return []
	except (json.JSONDecodeError, TypeError):
		return []


def _build_pe_filter_sql(payment_modes, categories, counterparties, pe_alias="pe"):
	"""Return (extra_joins, extra_where, extra_params) for Payment Entry queries.

	- payment_modes  → pe.mode_of_payment IN (…)
	- categories     → expense account names (5200-series); we look up parties
	                    who have Purchase Invoice items booked to those accounts
	- counterparties → pe.party IN (…)
	"""
	joins = ""
	where = ""
	params = []

	if payment_modes:
		placeholders = ", ".join(["%s"] * len(payment_modes))
		where += f" AND {pe_alias}.mode_of_payment IN ({placeholders})"
		params.extend(payment_modes)

	if categories:
		# Find full account names matching the selected category names
		cat_placeholders = ", ".join(["%s"] * len(categories))
		account_names = frappe.db.sql("""
			SELECT name FROM `tabAccount`
			WHERE account_name IN ({0}) AND root_type = 'Expense' AND is_group = 0
		""".format(cat_placeholders), categories, as_dict=True)

		if account_names:
			acct_names = [a.name for a in account_names]
			acct_ph = ", ".join(["%s"] * len(acct_names))
			# Find parties who have PI items booked to these expense accounts
			parties = frappe.db.sql("""
				SELECT DISTINCT pi.supplier AS party
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pi.docstatus = 1 AND pii.expense_account IN ({0})
			""".format(acct_ph), acct_names)
			party_list = [p[0] for p in parties if p[0]]

			if party_list:
				pp = ", ".join(["%s"] * len(party_list))
				where += f" AND {pe_alias}.party IN ({pp})"
				params.extend(party_list)
			else:
				# No matching parties — force empty result
				where += " AND 1=0"
		else:
			where += " AND 1=0"

	if counterparties:
		placeholders = ", ".join(["%s"] * len(counterparties))
		where += f" AND {pe_alias}.party IN ({placeholders})"
		params.extend(counterparties)

	return joins, where, params


# ── Filter-option endpoints ─────────────────────────────────────────────────

@frappe.whitelist()
def get_cashflow_filter_options():
	"""Return lists of unique payment modes, categories (expense accounts),
	   and counterparties from Payment Entries — for the filter dropdowns."""

	modes = frappe.db.sql("""
		SELECT DISTINCT pe.mode_of_payment
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.mode_of_payment IS NOT NULL AND pe.mode_of_payment != ''
		ORDER BY pe.mode_of_payment
	""", as_dict=True)

	# Categories = expense account names (5200-series children)
	categories = frappe.db.sql("""
		SELECT DISTINCT a.account_name
		FROM `tabAccount` a
		WHERE a.root_type = 'Expense' AND a.is_group = 0
			AND a.account_name NOT IN ('Cost of Goods Sold',
				'Expenses Included In Asset Valuation',
				'Expenses Included In Valuation',
				'Stock Adjustment', 'ERROR')
		ORDER BY a.account_name
	""", as_dict=True)

	counterparties = frappe.db.sql("""
		SELECT DISTINCT pe.party
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.party IS NOT NULL AND pe.party != ''
		ORDER BY pe.party
	""", as_dict=True)

	return {
		"payment_modes": [r.mode_of_payment for r in modes],
		"categories": [r.account_name for r in categories],
		"counterparties": [r.party for r in counterparties],
	}


# ── KPI Cards ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_cashflow_kpis(from_date=None, to_date=None,
                      payment_modes=None, categories=None, counterparties=None):
	"""Cash-flow page KPI strip with optional filters."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)
	has_filters = bool(p_modes or cats or cparts)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	if has_filters:
		_, where, params = _build_pe_filter_sql(p_modes, cats, cparts)
		cur_kpi = _get_filtered_cashflow_kpis(from_date, to_date, where, params)
		prev_kpi = _get_filtered_cashflow_kpis(prev_from_date, prev_to_date, where, params)

		data = {
			"cash_income": cur_kpi["cash_income"],
			"cash_income_change": calculate_change(cur_kpi["cash_income"], prev_kpi["cash_income"]),
			"transfer_income": cur_kpi["transfer_income"],
			"cash_expense": cur_kpi["cash_expense"],
			"cash_expense_change": calculate_change(cur_kpi["cash_expense"], prev_kpi["cash_expense"]),
			"transfer_expense": cur_kpi["transfer_expense"],
			"current_cash": get_cash_balance(),
			"current_transfer": get_transfer_balance(),
		}
		return data

	cash_income = get_cash_income_by_method(from_date, to_date, "Наличные")
	prev_cash_income = get_cash_income_by_method(prev_from_date, prev_to_date, "Наличные")

	cash_expense = get_cash_expense_by_method(from_date, to_date, "Наличные")
	prev_cash_expense = get_cash_expense_by_method(prev_from_date, prev_to_date, "Наличные")

	transfer_income = (
		get_cash_income_by_method(from_date, to_date, "Клик")
		+ get_cash_income_by_method(from_date, to_date, "Перечисление")
	)
	transfer_expense = (
		get_cash_expense_by_method(from_date, to_date, "Клик")
		+ get_cash_expense_by_method(from_date, to_date, "Перечисление")
	)

	data = {
		"cash_income": cash_income,
		"cash_income_change": calculate_change(cash_income, prev_cash_income),
		"transfer_income": transfer_income,
		"cash_expense": cash_expense,
		"cash_expense_change": calculate_change(cash_expense, prev_cash_expense),
		"transfer_expense": transfer_expense,
		"current_cash": get_cash_balance(),
		"current_transfer": get_transfer_balance(),
	}

	return data


def _get_filtered_cashflow_kpis(from_date, to_date, where, params):
	"""Compute cashflow KPIs with arbitrary WHERE clause."""
	result = frappe.db.sql("""
		SELECT
			SUM(CASE WHEN pe.payment_type='Receive' AND pe.mode_of_payment='Наличные'
				THEN pe.paid_amount ELSE 0 END) AS cash_income,
			SUM(CASE WHEN pe.payment_type='Receive' AND pe.mode_of_payment IN ('Клик','Перечисление')
				THEN pe.paid_amount ELSE 0 END) AS transfer_income,
			SUM(CASE WHEN pe.payment_type='Pay' AND pe.mode_of_payment='Наличные'
				THEN pe.paid_amount ELSE 0 END) AS cash_expense,
			SUM(CASE WHEN pe.payment_type='Pay' AND pe.mode_of_payment IN ('Клик','Перечисление')
				THEN pe.paid_amount ELSE 0 END) AS transfer_expense
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.posting_date BETWEEN %s AND %s
		{where}
	""".format(where=where), [from_date, to_date] + params, as_dict=True)
	r = result[0] if result else {}
	return {
		"cash_income": flt(r.get("cash_income"), 2),
		"transfer_income": flt(r.get("transfer_income"), 2),
		"cash_expense": flt(r.get("cash_expense"), 2),
		"transfer_expense": flt(r.get("transfer_expense"), 2),
	}


# ── Динамика прихода и расхода (bar chart) ──────────────────────────────────

@frappe.whitelist()
def get_income_expense_data(from_date=None, to_date=None,
                           payment_modes=None, categories=None, counterparties=None):
	"""Daily income / expense bars for the selected period."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)
	has_filters = bool(p_modes or cats or cparts)

	max_days = 30
	labels, income, expense = [], [], []
	cur = getdate(from_date)
	end = getdate(to_date)
	end = min(end, cur + timedelta(days=max_days - 1))

	if has_filters:
		_, where, params = _build_pe_filter_sql(p_modes, cats, cparts)
		while cur <= end:
			ds = cur.strftime("%Y-%m-%d")
			row = frappe.db.sql("""
				SELECT
					SUM(CASE WHEN pe.payment_type='Receive' THEN pe.paid_amount ELSE 0 END) AS inc,
					SUM(CASE WHEN pe.payment_type='Pay' THEN pe.paid_amount ELSE 0 END) AS exp
				FROM `tabPayment Entry` pe
				WHERE pe.docstatus = 1 AND pe.posting_date = %s
				{where}
			""".format(where=where), [ds] + params, as_dict=True)
			r = row[0] if row else {}
			labels.append(cur.strftime("%d.%m"))
			income.append(flt(r.get("inc"), 2))
			expense.append(flt(r.get("exp"), 2))
			cur += timedelta(days=1)
	else:
		while cur <= end:
			ds = cur.strftime("%Y-%m-%d")
			labels.append(cur.strftime("%d.%m"))
			income.append(flt(get_cash_flow_income(ds, ds), 2))
			expense.append(flt(get_cash_flow_expense(ds, ds), 2))
			cur += timedelta(days=1)

	return {
		"labels": labels,
		"income": income,
		"expense": expense,
	}


# ── Рейтинг приходов (table) ────────────────────────────────────────────────

@frappe.whitelist()
def get_income_ranking(from_date=None, to_date=None,
                      payment_modes=None, categories=None, counterparties=None):
	"""Top counterparties by incoming Payment Entry with change %."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	_, where, fparams = _build_pe_filter_sql(p_modes, cats, cparts)

	data = frappe.db.sql("""
		SELECT pe.party AS party, SUM(pe.paid_amount) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
			AND pe.posting_date BETWEEN %s AND %s
			AND pe.party IS NOT NULL AND pe.party != ''
			{where}
		GROUP BY pe.party
		ORDER BY amount DESC
	""".format(where=where),
		[from_date, to_date] + fparams, as_dict=True)

	if not data:
		if not (p_modes or cats or cparts):
			return _income_ranking_fallback(from_date, to_date)
		return []

	parties = [r.party for r in data]
	placeholders = ", ".join(["%s"] * len(parties))
	prev_rows = frappe.db.sql("""
		SELECT pe.party, SUM(pe.paid_amount) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
			AND pe.posting_date BETWEEN %s AND %s
			AND pe.party IN ({0})
		GROUP BY pe.party
	""".format(placeholders), [prev_from_date, prev_to_date] + parties, as_dict=True)
	prev_map = {r.party: flt(r.amount) for r in prev_rows}

	return [{
		"party": row.party,
		"amount": flt(row.amount, 2),
		"change": flt(calculate_change(row.amount, prev_map.get(row.party, 0)), 1),
	} for row in data]


# ── Рейтинг расходов (table) ────────────────────────────────────────────────

@frappe.whitelist()
def get_expense_ranking(from_date=None, to_date=None,
                       payment_modes=None, categories=None, counterparties=None):
	"""Top expense parties from Payment Entry with change %."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	_, where, fparams = _build_pe_filter_sql(p_modes, cats, cparts)

	data = frappe.db.sql("""
		SELECT pe.party AS party, SUM(pe.paid_amount) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Pay'
			AND pe.posting_date BETWEEN %s AND %s
			AND pe.party IS NOT NULL AND pe.party != ''
			{where}
		GROUP BY pe.party
		ORDER BY amount DESC
	""".format(where=where),
		[from_date, to_date] + fparams, as_dict=True)

	if not data:
		if not (p_modes or cats or cparts):
			return _expense_ranking_fallback(from_date, to_date)
		return []

	parties = [r.party for r in data]
	placeholders = ", ".join(["%s"] * len(parties))
	prev_rows = frappe.db.sql("""
		SELECT pe.party, SUM(pe.paid_amount) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1 AND pe.payment_type = 'Pay'
			AND pe.posting_date BETWEEN %s AND %s
			AND pe.party IN ({0})
		GROUP BY pe.party
	""".format(placeholders), [prev_from_date, prev_to_date] + parties, as_dict=True)
	prev_map = {r.party: flt(r.amount) for r in prev_rows}

	return [{
		"category": row.party or "Без категории",
		"amount": flt(row.amount, 2),
		"change": flt(calculate_change(row.amount, prev_map.get(row.party, 0)), 1),
	} for row in data]


# ── Данные по обороту (detail table) ────────────────────────────────────────

@frappe.whitelist()
def get_cashflow_data(from_date=None, to_date=None,
                     payment_modes=None, categories=None, counterparties=None):
	"""Detailed cash-flow rows from Payment Entry with optional filters."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)

	_, where, fparams = _build_pe_filter_sql(p_modes, cats, cparts)

	data = frappe.db.sql("""
		SELECT pe.posting_date AS date, pe.mode_of_payment,
			   pe.payment_type, pe.party_type, pe.party,
			   pe.paid_amount AS amount,
			   pe.paid_to_account_currency AS currency,
			   pe.remarks AS comment
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.posting_date BETWEEN %s AND %s
			{where}
		ORDER BY pe.posting_date DESC, pe.name DESC
		LIMIT 500
	""".format(where=where),
		[from_date, to_date] + fparams, as_dict=True)

	flow_type_map = {"Receive": "Приход", "Pay": "Расход", "Internal Transfer": "Перевод"}

	return [{
		"date": r.date.strftime("%d.%m.%Y") if r.date else "",
		"payment_method": r.mode_of_payment or "",
		"flow_type": flow_type_map.get(r.payment_type, r.payment_type or ""),
		"category": r.party_type or "",
		"category_2": "",
		"counterparty": r.party or "",
		"amount": flt(r.amount, 2),
		"amount_uzs": 0,
		"comment": r.comment or "",
	} for r in data]


# ── Данные по обороту — сводка (bottom-right table) ─────────────────────────

@frappe.whitelist()
def get_turnover_summary(from_date=None, to_date=None,
                        payment_modes=None, categories=None, counterparties=None):
	"""Turnover summary by payment type with optional filters."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	p_modes = _parse_json_list(payment_modes)
	cats = _parse_json_list(categories)
	cparts = _parse_json_list(counterparties)
	has_filters = bool(p_modes or cats or cparts)

	if has_filters:
		_, where, fparams = _build_pe_filter_sql(p_modes, cats, cparts)
		result = frappe.db.sql("""
			SELECT pe.mode_of_payment,
				SUM(CASE WHEN pe.payment_type='Pay' THEN pe.paid_amount ELSE 0 END) AS expense,
				SUM(CASE WHEN pe.payment_type='Receive' THEN pe.paid_amount ELSE 0 END) AS income
			FROM `tabPayment Entry` pe
			WHERE pe.docstatus = 1 AND pe.posting_date BETWEEN %s AND %s
				{where}
			GROUP BY pe.mode_of_payment
		""".format(where=where), [from_date, to_date] + fparams, as_dict=True)
		mode_map = {r.mode_of_payment: r for r in result}
		return [
			{"payment_type": m,
			 "expense": flt(mode_map.get(m, {}).get("expense"), 2),
			 "income": flt(mode_map.get(m, {}).get("income"), 2)}
			for m in ["Наличные", "Клик", "Перечисление"]
		]

	return [
		{
			"payment_type": "Наличные",
			"expense": get_cash_expense_by_method(from_date, to_date, "Наличные"),
			"income": get_cash_income_by_method(from_date, to_date, "Наличные"),
		},
		{
			"payment_type": "Клик",
			"expense": get_cash_expense_by_method(from_date, to_date, "Клик"),
			"income": get_cash_income_by_method(from_date, to_date, "Клик"),
		},
		{
			"payment_type": "Перечисление",
			"expense": get_cash_expense_by_method(from_date, to_date, "Перечисление"),
			"income": get_cash_income_by_method(from_date, to_date, "Перечисление"),
		},
	]


# ── Private fallbacks ────────────────────────────────────────────────────────

def _income_ranking_fallback(from_date, to_date):
	"""Fallback: Sales Invoice grouped by customer."""
	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	try:
		data = frappe.db.sql("""
			SELECT si.customer AS party, SUM(si.grand_total) AS amount
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
			GROUP BY si.customer ORDER BY amount DESC
		""", (from_date, to_date), as_dict=True)

		if not data:
			return []

		parties = [r.party for r in data]
		placeholders = ", ".join(["%s"] * len(parties))
		prev_rows = frappe.db.sql("""
			SELECT si.customer AS party, SUM(si.grand_total) AS amount
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
				AND si.customer IN ({0})
			GROUP BY si.customer
		""".format(placeholders), [prev_from_date, prev_to_date] + parties, as_dict=True)
		prev_map = {r.party: flt(r.amount) for r in prev_rows}

		return [{
			"party": r.party or "",
			"amount": flt(r.amount, 2),
			"change": flt(calculate_change(flt(r.amount), prev_map.get(r.party, 0)), 1),
		} for r in data]
	except Exception:
		return []


def _expense_ranking_fallback(from_date, to_date):
	"""Fallback: Purchase Invoice + Journal Entry expenses."""
	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	expenses = {}
	prev_expenses = {}

	# Purchase Invoice Items
	try:
		for target, fd, td in [
			(expenses, from_date, to_date),
			(prev_expenses, prev_from_date, prev_to_date),
		]:
			rows = frappe.db.sql("""
				SELECT IFNULL(SUBSTRING_INDEX(pii.expense_account, ' - ', 1),
					'Без категории') AS category, SUM(pii.amount) AS amount
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %s AND %s
				GROUP BY category
			""", (fd, td), as_dict=True)
			for r in rows:
				target[r.category] = target.get(r.category, 0) + flt(r.amount)
	except Exception:
		pass

	# Journal Entry
	try:
		for target, fd, td in [
			(expenses, from_date, to_date),
			(prev_expenses, prev_from_date, prev_to_date),
		]:
			rows = frappe.db.sql("""
				SELECT IFNULL(SUBSTRING_INDEX(jea.account, ' - ', 1),
					'Без категории') AS category,
					SUM(jea.debit_in_account_currency) AS amount
				FROM `tabJournal Entry Account` jea
				INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
				INNER JOIN `tabAccount` acc ON acc.name = jea.account
				WHERE je.docstatus = 1 AND je.posting_date BETWEEN %s AND %s
					AND acc.root_type = 'Expense' AND jea.debit_in_account_currency > 0
				GROUP BY category
			""", (fd, td), as_dict=True)
			for r in rows:
				target[r.category] = target.get(r.category, 0) + flt(r.amount)
	except Exception:
		pass

	if not expenses:
		return []

	sorted_exp = sorted(expenses.items(), key=lambda x: x[1], reverse=True)
	return [{
		"category": cat,
		"amount": flt(amt, 2),
		"change": flt(calculate_change(amt, prev_expenses.get(cat, 0)), 1),
	} for cat, amt in sorted_exp]
