# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
ГОТОВАЯ ПРОДУКЦИЯ (Finished goods stock page)
──────────────────────────────────────────────
Items of item group "Готовый продукт" with stock on hand, grouped by the
first 2 letters of the item name (e.g. "ХБ", "1_", "С_").

Stock is taken as of `to_date` from Stock Ledger Entry (latest
qty_after_transaction per item+warehouse) — same logic as the СКЛАД page.

Filters: to_date, warehouses (list), prefixes (list), search (text)
"""

import frappe
from frappe.utils import flt, getdate, nowdate

from armada.armada_custom_app.api.warehouse import _get_stock_as_of, _parse_json_list

FINISHED_GOODS_GROUP = "Готовый продукт"


def _prefix(item_name):
	"""First 2 letters/digits of the item name, case-insensitive.

	Separators ("_", ".", "-") between them are kept but not counted, and
	spaces are dropped: "1_ 3 - ..." → "1_3", "1_6 - ..." → "1_6",
	"Хб_а - ..." → "ХБ".
	"""
	out, count = "", 0
	# Only look at the model part before " - " (the size part follows it)
	for ch in (item_name or "").split(" - ")[0]:
		if ch.isspace():
			continue
		if ch.isalnum():
			out += ch
			count += 1
			if count == 2:
				break
		elif count:  # separator between the 2 chars; skip leading ones
			out += ch
	return out.upper() or "—"


@frappe.whitelist()
def get_finished_goods_filter_options():
	"""Warehouses holding finished goods and all 2-letter name prefixes."""
	names = frappe.get_all(
		"Item",
		filters={"item_group": FINISHED_GOODS_GROUP, "disabled": 0},
		pluck="item_name",
	)
	prefixes = sorted({_prefix(n) for n in names})

	warehouses = frappe.db.sql("""
		SELECT DISTINCT b.warehouse
		FROM `tabBin` b
		JOIN `tabItem` item ON item.name = b.item_code
		WHERE item.item_group = %s
		ORDER BY b.warehouse
	""", FINISHED_GOODS_GROUP, pluck=True)

	return {"warehouses": warehouses, "prefixes": prefixes}


@frappe.whitelist()
def get_finished_goods_stock(to_date=None, warehouses=None, prefixes=None, search=None):
	"""Finished goods stock grouped by name prefix.

	Returns {kpis, warehouses, groups: [{prefix, item_count, total_qty,
	total_value, items: [{item_code, item_name, qty, value, rate, by_warehouse}]}]}
	"""
	to_date = getdate(to_date or nowdate())
	wh_list = _parse_json_list(warehouses)
	prefix_set = {p.upper() for p in _parse_json_list(prefixes)}
	search = (search or "").strip().lower()

	rows = _get_stock_as_of(to_date, wh_list, [FINISHED_GOODS_GROUP], [])

	items = {}
	used_warehouses = set()
	for r in rows:
		if flt(r.actual_qty) == 0:
			continue
		name = r.item_name or r.item_code
		prefix = _prefix(name)
		if prefix_set and prefix not in prefix_set:
			continue
		if search and search not in name.lower() and search not in (r.item_code or "").lower():
			continue

		it = items.setdefault(r.item_code, {
			"item_code": r.item_code,
			"item_name": name,
			"prefix": prefix,
			"qty": 0.0,
			"value": 0.0,
			"by_warehouse": {},
		})
		it["qty"] += flt(r.actual_qty)
		it["value"] += flt(r.stock_value)
		it["by_warehouse"][r.warehouse] = it["by_warehouse"].get(r.warehouse, 0) + flt(r.actual_qty)
		used_warehouses.add(r.warehouse)

	groups = {}
	for it in items.values():
		it["rate"] = flt(it["value"] / it["qty"], 2) if it["qty"] else 0
		it["qty"] = flt(it["qty"], 2)
		it["value"] = flt(it["value"], 2)
		g = groups.setdefault(it["prefix"], {
			"prefix": it["prefix"], "item_count": 0, "total_qty": 0.0, "total_value": 0.0, "items": [],
		})
		g["item_count"] += 1
		g["total_qty"] += it["qty"]
		g["total_value"] += it["value"]
		g["items"].append(it)

	group_list = sorted(groups.values(), key=lambda g: g["total_qty"], reverse=True)
	for g in group_list:
		g["total_qty"] = flt(g["total_qty"], 2)
		g["total_value"] = flt(g["total_value"], 2)
		g["items"].sort(key=lambda i: i["item_name"])

	return {
		"kpis": {
			"total_qty": flt(sum(g["total_qty"] for g in group_list), 2),
			"total_value": flt(sum(g["total_value"] for g in group_list), 2),
			"item_count": len(items),
			"group_count": len(group_list),
		},
		"warehouses": sorted(used_warehouses),
		"groups": group_list,
	}
