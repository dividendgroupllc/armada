# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
ПРОДАЖИ (Sales Page)
────────────────────
All data from ERPNext standard doctypes:
  Sales Invoice / Sales Invoice Item — for sales
  Purchase Invoice / Purchase Invoice Item — for purchases

Filters: item_names (list), item_groups / "Типаж" (list), customers (list)

KPI cards: Количество проданных, Сумма продаж, Сумма себестоимости,
           Общая маржа, Средняя цена, Рентабельность
Charts:    Годовая динамика продаж (bar)
Tables:    Данные по продажам, Рейтинг по продажам продуктов
"""

import json
import frappe
from frappe import _
from frappe.utils import nowdate, add_months, get_first_day, flt
from datetime import datetime
import calendar

from armada.armada_custom_app.api.utils import (
	calculate_change,
	calculate_profitability,
	get_total_sales,
	get_sales_summary,
	get_purchases_summary,
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


def _build_item_filter_sql(item_names, item_groups, customers,
                           si_alias="si", sii_alias="sii"):
	"""Return (extra_joins, extra_where, extra_params) for Sales Invoice queries."""
	joins = ""
	where = ""
	params = []

	if item_groups:
		joins += f" INNER JOIN `tabItem` _flt_item ON _flt_item.name = {sii_alias}.item_code"
		placeholders = ", ".join(["%s"] * len(item_groups))
		where += f" AND _flt_item.item_group IN ({placeholders})"
		params.extend(item_groups)

	if item_names:
		placeholders = ", ".join(["%s"] * len(item_names))
		where += f" AND {sii_alias}.item_name IN ({placeholders})"
		params.extend(item_names)

	if customers:
		placeholders = ", ".join(["%s"] * len(customers))
		where += f" AND {si_alias}.customer IN ({placeholders})"
		params.extend(customers)

	return joins, where, params


# ── Filter-option endpoints ─────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_filter_options():
	"""Return lists of unique item_names, item_groups (Типаж), and customers
	   that appear in submitted Sales Invoices — for the filter dropdowns."""

	items = frappe.db.sql("""
		SELECT DISTINCT sii.item_name
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND sii.item_name IS NOT NULL AND sii.item_name != ''
		ORDER BY sii.item_name
	""", as_dict=True)

	groups = frappe.db.sql("""
		SELECT DISTINCT ig.name AS item_group
		FROM `tabItem Group` ig
		INNER JOIN `tabItem` item ON item.item_group = ig.name
		INNER JOIN `tabSales Invoice Item` sii ON sii.item_code = item.name
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
		ORDER BY ig.name
	""", as_dict=True)

	customers = frappe.db.sql("""
		SELECT DISTINCT si.customer
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.customer IS NOT NULL AND si.customer != ''
		ORDER BY si.customer
	""", as_dict=True)

	return {
		"item_names": [r.item_name for r in items],
		"item_groups": [r.item_group for r in groups],
		"customers": [r.customer for r in customers],
	}


# ── KPI Cards ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_kpis(from_date=None, to_date=None,
                   item_names=None, item_groups=None, customers=None):
	"""Sales page KPI strip with optional multi-select filters."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	i_names = _parse_json_list(item_names)
	i_groups = _parse_json_list(item_groups)
	custs = _parse_json_list(customers)

	has_filters = bool(i_names or i_groups or custs)

	if has_filters:
		cur = _get_filtered_sales_summary(from_date, to_date, i_names, i_groups, custs)
		prev_from = add_months(from_date, -1)
		prev_to = add_months(to_date, -1)
		prev = _get_filtered_sales_summary(prev_from, prev_to, i_names, i_groups, custs)
	else:
		prev_from = add_months(from_date, -1)
		prev_to = add_months(to_date, -1)
		cur = get_sales_summary(from_date, to_date)
		prev = get_sales_summary(prev_from, prev_to)

	qty = cur.get("qty", 0)
	amount = cur.get("amount", 0)
	cost = cur.get("cost", 0)

	return {
		"sold_qty": qty,
		"sold_change": calculate_change(qty, prev.get("qty", 0)),
		"sales_amount": amount,
		"sales_amount_change": calculate_change(amount, prev.get("amount", 0)),
		"cost_amount": cost,
		"total_margin": amount - cost,
		"avg_price": amount / qty if qty > 0 else 0,
		"profitability": calculate_profitability(amount, cost),
	}


def _get_filtered_sales_summary(from_date, to_date, item_names, item_groups, customers):
	"""Sales summary with multi-select filters applied."""
	joins, where, params = _build_item_filter_sql(item_names, item_groups, customers)
	result = frappe.db.sql("""
		SELECT
			SUM(sii.qty) AS qty,
			SUM(sii.amount) AS amount,
			SUM(IFNULL(sii.incoming_rate, 0) * sii.qty) AS cost
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{joins}
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
		{where}
	""".format(joins=joins, where=where),
		[from_date, to_date] + params, as_dict=True)

	if result and result[0]:
		return {
			"qty": flt(result[0].qty, 0),
			"amount": flt(result[0].amount, 2),
			"cost": flt(result[0].cost, 2),
		}
	return {"qty": 0, "amount": 0, "cost": 0}


# ── Годовая динамика продаж (bar chart) ─────────────────────────────────────

@frappe.whitelist()
def get_sales_dynamics(item_names=None, item_groups=None, customers=None):
	"""Monthly sales bars for the current year with optional filters."""
	i_names = _parse_json_list(item_names)
	i_groups = _parse_json_list(item_groups)
	custs = _parse_json_list(customers)

	year = datetime.now().year
	fd = f"{year}-01-01"
	td = f"{year}-12-31"

	month_names = [
		'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
		'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
	]

	joins, where, fparams = _build_item_filter_sql(i_names, i_groups, custs)

	rows = frappe.db.sql("""
		SELECT MONTH(si.posting_date) AS m, SUM(sii.amount) AS amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{joins}
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
		{where}
		GROUP BY MONTH(si.posting_date)
	""".format(joins=joins, where=where),
		[fd, td] + fparams, as_dict=True)

	month_map = {r.m: flt(r.amount, 2) for r in rows}

	labels = month_names[:]
	values = [month_map.get(m, 0) for m in range(1, 13)]

	return {"labels": labels, "values": values}


# ── Рейтинг по продажам продуктов (table) ───────────────────────────────────

@frappe.whitelist()
def get_product_ranking(from_date=None, to_date=None,
                       item_names=None, item_groups=None, customers=None):
	"""Top products by sales amount with change % from Sales Invoice Items."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	i_names = _parse_json_list(item_names)
	i_groups = _parse_json_list(item_groups)
	custs = _parse_json_list(customers)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	joins, where, fparams = _build_item_filter_sql(i_names, i_groups, custs)

	data = frappe.db.sql("""
		SELECT sii.item_code, sii.item_name, SUM(sii.qty) AS qty,
			   SUM(sii.amount) AS amount,
			   SUM(IFNULL(sii.incoming_rate, 0) * sii.qty) AS cost
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{joins}
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
		{where}
		GROUP BY sii.item_code, sii.item_name
		ORDER BY amount DESC
	""".format(joins=joins, where=where),
		[from_date, to_date] + fparams, as_dict=True)

	if not data:
		return []

	item_codes = [r.item_code for r in data]
	placeholders = ", ".join(["%s"] * len(item_codes))
	prev_rows = frappe.db.sql("""
		SELECT sii.item_code, SUM(sii.amount) AS amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{joins}
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
			AND sii.item_code IN ({placeholders})
		{where}
		GROUP BY sii.item_code
	""".format(joins=joins, placeholders=placeholders, where=where),
		[prev_from_date, prev_to_date] + fparams + item_codes, as_dict=True)
	prev_map = {r.item_code: flt(r.amount) for r in prev_rows}

	result = []
	for r in data:
		cost = flt(r.cost, 2)
		amt = flt(r.amount, 2)
		result.append({
			"item_code": r.item_code or "",
			"item_name": r.item_name or "",
			"qty": flt(r.qty, 0),
			"amount": amt,
			"cost": cost,
			"margin": flt(amt - cost, 2),
			"change": flt(calculate_change(amt, prev_map.get(r.item_code, 0)), 1),
		})
	return result


# ── Данные по продажам (table) ───────────────────────────────────────────────

@frappe.whitelist()
def get_sales_data(from_date=None, to_date=None,
                   item_names=None, item_groups=None, customers=None):
	"""Detailed sales rows from Sales Invoice + Items with optional filters."""
	from_date, to_date = get_smart_date_range(from_date, to_date)
	i_names = _parse_json_list(item_names)
	i_groups = _parse_json_list(item_groups)
	custs = _parse_json_list(customers)

	joins, where, fparams = _build_item_filter_sql(i_names, i_groups, custs)

	data = frappe.db.sql("""
		SELECT si.posting_date AS date, sii.item_name, si.customer, sii.qty, sii.amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{joins}
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
		{where}
		ORDER BY si.posting_date DESC, si.name DESC
		LIMIT 500
	""".format(joins=joins, where=where),
		[from_date, to_date] + fparams, as_dict=True)

	return [{
		"date": r.date.strftime("%d.%m.%Y") if r.date else "",
		"item_name": r.item_name or "",
		"customer": r.customer or "",
		"qty": flt(r.qty, 0),
		"amount": flt(r.amount, 2),
	} for r in data]


# ── Purchases helpers (used by main KPI) ─────────────────────────────────────

@frappe.whitelist()
def get_purchases_kpis(from_date=None, to_date=None):
	"""Purchases KPI strip."""
	from_date, to_date = get_smart_date_range(from_date, to_date)

	prev_from_date = add_months(from_date, -1)
	prev_to_date = add_months(to_date, -1)

	cur = get_purchases_summary(from_date, to_date)
	prev = get_purchases_summary(prev_from_date, prev_to_date)

	return {
		"purchase_qty": cur.get("qty", 0),
		"purchase_qty_change": calculate_change(cur.get("qty", 0), prev.get("qty", 0)),
		"purchase_amount": cur.get("amount", 0),
		"purchase_amount_change": calculate_change(cur.get("amount", 0), prev.get("amount", 0)),
		"raw_materials": cur.get("raw_materials", 0),
		"avg_rate": cur.get("amount", 0) / cur.get("qty", 1) if cur.get("qty", 0) > 0 else 0,
	}


@frappe.whitelist()
def get_purchase_data(from_date=None, to_date=None):
	"""Detailed purchase rows from Purchase Invoice + Items."""
	from_date, to_date = get_smart_date_range(from_date, to_date)

	data = frappe.db.sql("""
		SELECT pi.posting_date AS date, pii.item_name,
			   pi.supplier, pii.qty, pii.uom, pii.rate, pii.amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %s AND %s
		ORDER BY pi.posting_date DESC, pi.name DESC
	""", (from_date, to_date), as_dict=True)

	return [{
		"date": r.date.strftime("%d.%m.%Y") if r.date else "",
		"item_name": r.item_name or "",
		"supplier": r.supplier or "",
		"qty": flt(r.qty, 2),
		"uom": r.uom or "",
		"rate": flt(r.rate, 2),
		"amount": flt(r.amount, 2),
		"type": "",
	} for r in data]


@frappe.whitelist()
def get_supplier_ranking(from_date=None, to_date=None):
	"""Top suppliers by purchase amount from Purchase Invoice."""
	from_date, to_date = get_smart_date_range(from_date, to_date)

	data = frappe.db.sql("""
		SELECT pi.supplier, SUM(pi.grand_total) AS amount, COUNT(*) AS count
		FROM `tabPurchase Invoice` pi
		WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %s AND %s
			AND pi.supplier IS NOT NULL AND pi.supplier != ''
		GROUP BY pi.supplier
		ORDER BY amount DESC
	""", (from_date, to_date), as_dict=True)

	return [{
		"supplier": r.supplier,
		"amount": flt(r.amount, 2),
		"count": r.count,
	} for r in data]
