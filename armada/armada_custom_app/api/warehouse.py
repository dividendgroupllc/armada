# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
СКЛАД (Warehouse / Stock Page)
───────────────────────────────
All data from ERPNext standard doctype:
  Bin — current stock per item_code + warehouse

Filters: warehouses (list), item_groups (list), items (list)

KPI cards: Общее кол-во, Общая стоимость, Кол-во складов, Кол-во наименований
Tables:    Остаток по складам, Детальные данные по складу
"""

import json
import frappe
from frappe import _
from frappe.utils import flt


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


def _build_bin_filter_sql(warehouses, item_groups, items, bin_alias="b"):
	"""Return (extra_where, extra_params, need_item_join) for Bin queries."""
	where = ""
	params = []
	need_item_join = False

	if warehouses:
		placeholders = ", ".join(["%s"] * len(warehouses))
		where += f" AND {bin_alias}.warehouse IN ({placeholders})"
		params.extend(warehouses)

	if item_groups:
		placeholders = ", ".join(["%s"] * len(item_groups))
		where += f" AND item.item_group IN ({placeholders})"
		params.extend(item_groups)
		need_item_join = True

	if items:
		placeholders = ", ".join(["%s"] * len(items))
		where += f" AND {bin_alias}.item_code IN ({placeholders})"
		params.extend(items)

	return where, params, need_item_join


# ── Filter-option endpoints ─────────────────────────────────────────────────

@frappe.whitelist()
def get_warehouse_filter_options():
	"""Return all non-group warehouses, item groups and items for the filter dropdowns."""

	warehouses = frappe.db.sql("""
		SELECT name
		FROM `tabWarehouse`
		WHERE disabled = 0 AND is_group = 0
		ORDER BY name
	""", as_dict=True)

	item_groups = frappe.db.sql("""
		SELECT name
		FROM `tabItem Group`
		WHERE is_group = 0
		ORDER BY name
	""", as_dict=True)

	items = frappe.db.sql("""
		SELECT name, item_name
		FROM `tabItem`
		WHERE disabled = 0 AND is_stock_item = 1
		ORDER BY item_name
	""", as_dict=True)

	return {
		"warehouses": [r.name for r in warehouses],
		"item_groups": [r.name for r in item_groups],
		"items": [r.name for r in items],
	}


# ── KPI Cards ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_warehouse_kpis(warehouses=None, item_groups=None, items=None):
	"""Warehouse page KPI strip with optional multi-select filters."""
	wh_list = _parse_json_list(warehouses)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	where, params, need_item_join = _build_bin_filter_sql(wh_list, ig_list, item_list)

	item_join = "JOIN `tabItem` item ON item.name = b.item_code" if need_item_join else ""

	result = frappe.db.sql("""
		SELECT
			SUM(b.actual_qty) AS total_qty,
			SUM(b.stock_value) AS total_value,
			COUNT(DISTINCT b.item_code) AS item_count
		FROM `tabBin` b
		{item_join}
		WHERE 1=1
		{where}
	""".format(item_join=item_join, where=where), params, as_dict=True)

	# Warehouse count from tabWarehouse (actual count, not from Bin)
	if wh_list:
		placeholders = ", ".join(["%s"] * len(wh_list))
		wh_count = frappe.db.sql("""
			SELECT COUNT(*) AS cnt
			FROM `tabWarehouse`
			WHERE disabled = 0 AND is_group = 0
				AND name IN ({placeholders})
		""".format(placeholders=placeholders), wh_list, as_dict=True)
	else:
		wh_count = frappe.db.sql("""
			SELECT COUNT(*) AS cnt
			FROM `tabWarehouse`
			WHERE disabled = 0 AND is_group = 0
		""", as_dict=True)

	r = result[0] if result else {}
	return {
		"total_qty": flt(r.get("total_qty"), 2),
		"total_value": flt(r.get("total_value"), 2),
		"warehouse_count": wh_count[0].cnt if wh_count else 0,
		"item_count": r.get("item_count") or 0,
	}


# ── Остаток по складам (summary table) ──────────────────────────────────────

@frappe.whitelist()
def get_warehouse_summary(warehouses=None, item_groups=None, items=None):
	"""Stock summary grouped by warehouse."""
	wh_list = _parse_json_list(warehouses)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	where, params, need_item_join = _build_bin_filter_sql(wh_list, ig_list, item_list)

	item_join = "JOIN `tabItem` item ON item.name = b.item_code" if need_item_join else ""

	data = frappe.db.sql("""
		SELECT
			b.warehouse,
			SUM(b.actual_qty) AS total_qty,
			SUM(b.stock_value) AS total_value,
			COUNT(DISTINCT b.item_code) AS item_count
		FROM `tabBin` b
		{item_join}
		WHERE 1=1
		{where}
		GROUP BY b.warehouse
		ORDER BY total_value DESC
	""".format(item_join=item_join, where=where), params, as_dict=True)

	return [{
		"warehouse": r.warehouse or "",
		"total_qty": flt(r.total_qty, 2),
		"total_value": flt(r.total_value, 2),
		"item_count": r.item_count or 0,
	} for r in data]


# ── Детальные данные по складу (detail table) ────────────────────────────────

@frappe.whitelist()
def get_warehouse_stock_data(warehouses=None, item_groups=None, items=None):
	"""Detailed stock rows from Bin with optional filters."""
	wh_list = _parse_json_list(warehouses)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	where, params, need_item_join = _build_bin_filter_sql(wh_list, ig_list, item_list)

	# Always join tabItem to get item_name and item_group
	data = frappe.db.sql("""
		SELECT
			b.item_code,
			IFNULL(item.item_name, b.item_code) AS item_name,
			item.item_group,
			b.warehouse,
			b.actual_qty,
			b.valuation_rate,
			b.stock_value
		FROM `tabBin` b
		LEFT JOIN `tabItem` item ON item.name = b.item_code
		WHERE 1=1
		{where}
		ORDER BY b.stock_value DESC
		LIMIT 500
	""".format(where=where), params, as_dict=True)

	return [{
		"item_code": r.item_code or "",
		"item_name": r.item_name or "",
		"item_group": r.item_group or "",
		"warehouse": r.warehouse or "",
		"actual_qty": flt(r.actual_qty, 2),
		"valuation_rate": flt(r.valuation_rate, 2),
		"stock_value": flt(r.stock_value, 2),
	} for r in data]
