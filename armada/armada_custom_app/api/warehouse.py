# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
СКЛАД (Warehouse / Stock Page)
───────────────────────────────
All data from ERPNext standard doctypes:
  Bin                — current stock per item_code + warehouse (no date filter)
  Stock Ledger Entry — stock balance as of a chosen date (when to_date is passed)

Filters: warehouses (list), item_groups (list), items (list), from_date/to_date

KPI cards: Общее кол-во, Общая стоимость, Кол-во наименований
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
	if isinstance(val, str) and val and not val.strip().startswith("["):
		return [val]
	try:
		parsed = json.loads(val)
		if isinstance(parsed, list):
			return [v for v in parsed if v]
		return []
	except (json.JSONDecodeError, TypeError):
		return []


def _merge_warehouse_filters(warehouses=None, warehouse=None):
	"""Merge warehouse multi-select and single warehouse inputs into one list."""
	merged = _parse_json_list(warehouses)
	if warehouse:
		merged.extend(_parse_json_list(warehouse))
	# Keep order but remove duplicates
	return list(dict.fromkeys([w for w in merged if w]))


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


def _get_stock_as_of(to_date, warehouses, item_groups, items):
	"""Stock balance per item_code + warehouse as of to_date (inclusive).

	Uses the latest SLE's qty_after_transaction / stock_value per item+warehouse
	(NOT SUM(actual_qty)) so Stock Reconciliation resets are respected —
	same approach as ERPNext's Stock Balance report.
	"""
	inner_where = ""
	inner_params = []
	if warehouses:
		placeholders = ", ".join(["%s"] * len(warehouses))
		inner_where += f" AND sle.warehouse IN ({placeholders})"
		inner_params.extend(warehouses)
	if items:
		placeholders = ", ".join(["%s"] * len(items))
		inner_where += f" AND sle.item_code IN ({placeholders})"
		inner_params.extend(items)

	outer_where = ""
	outer_params = []
	if item_groups:
		placeholders = ", ".join(["%s"] * len(item_groups))
		outer_where += f" AND item.item_group IN ({placeholders})"
		outer_params.extend(item_groups)

	return frappe.db.sql("""
		SELECT
			t.item_code,
			IFNULL(item.item_name, t.item_code) AS item_name,
			item.item_group,
			t.warehouse,
			t.qty_after_transaction AS actual_qty,
			t.valuation_rate,
			t.stock_value
		FROM (
			SELECT
				sle.item_code,
				sle.warehouse,
				sle.qty_after_transaction,
				sle.valuation_rate,
				sle.stock_value,
				ROW_NUMBER() OVER (
					PARTITION BY sle.item_code, sle.warehouse
					ORDER BY sle.posting_datetime DESC, sle.creation DESC
				) AS rn
			FROM `tabStock Ledger Entry` sle
			WHERE sle.is_cancelled = 0
				AND sle.posting_date <= %s
				{inner_where}
		) t
		LEFT JOIN `tabItem` item ON item.name = t.item_code
		WHERE t.rn = 1
			AND (t.qty_after_transaction != 0 OR ABS(t.stock_value) > 0.005)
			{outer_where}
	""".format(inner_where=inner_where, outer_where=outer_where),
		[to_date] + inner_params + outer_params, as_dict=True)


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
def get_warehouse_kpis(warehouses=None, warehouse=None, item_groups=None, items=None,
		from_date=None, to_date=None):
	"""Warehouse page KPI strip with optional multi-select and date filters."""
	wh_list = _merge_warehouse_filters(warehouses, warehouse)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	if to_date:
		rows = _get_stock_as_of(to_date, wh_list, ig_list, item_list)
		return {
			"total_qty": flt(sum(flt(r.actual_qty) for r in rows), 2),
			"total_value": flt(sum(flt(r.stock_value) for r in rows), 2),
			"item_count": len({r.item_code for r in rows}),
		}

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

	r = result[0] if result else {}
	return {
		"total_qty": flt(r.get("total_qty"), 2),
		"total_value": flt(r.get("total_value"), 2),
		"item_count": r.get("item_count") or 0,
	}


# ── Остаток по складам (summary table) ──────────────────────────────────────

@frappe.whitelist()
def get_warehouse_summary(warehouses=None, warehouse=None, item_groups=None, items=None,
		from_date=None, to_date=None):
	"""Stock summary grouped by warehouse."""
	wh_list = _merge_warehouse_filters(warehouses, warehouse)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	if to_date:
		rows = _get_stock_as_of(to_date, wh_list, ig_list, item_list)
		grouped = {}
		for r in rows:
			g = grouped.setdefault(r.warehouse, {"total_qty": 0, "total_value": 0, "items": set()})
			g["total_qty"] += flt(r.actual_qty)
			g["total_value"] += flt(r.stock_value)
			g["items"].add(r.item_code)
		return sorted([{
			"warehouse": wh or "",
			"total_qty": flt(g["total_qty"], 2),
			"total_value": flt(g["total_value"], 2),
			"item_count": len(g["items"]),
		} for wh, g in grouped.items()], key=lambda x: x["total_value"], reverse=True)

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
def get_warehouse_stock_data(warehouses=None, warehouse=None, item_groups=None, items=None,
		from_date=None, to_date=None):
	"""Detailed stock rows from Bin, or from SLE as of to_date when given."""
	wh_list = _merge_warehouse_filters(warehouses, warehouse)
	ig_list = _parse_json_list(item_groups)
	item_list = _parse_json_list(items)

	if to_date:
		rows = _get_stock_as_of(to_date, wh_list, ig_list, item_list)
		rows.sort(key=lambda r: flt(r.stock_value), reverse=True)
		return [{
			"item_code": r.item_code or "",
			"item_name": r.item_name or "",
			"item_group": r.item_group or "",
			"warehouse": r.warehouse or "",
			"actual_qty": flt(r.actual_qty, 2),
			"valuation_rate": flt(r.valuation_rate, 2),
			"stock_value": flt(r.stock_value, 2),
		} for r in rows[:500]]

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
