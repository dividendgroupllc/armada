# Copyright (c) 2026, Sherzod Rohatov and contributors
# For license information, please see license.txt

"""
Armada Dashboard API — Backward-compatible router.

The actual logic now lives in dedicated modules:
  • main.py           — ГЛАВНАЯ page
  • sales.py          — ПРОДАЖИ page
  • cashflow.py       — ДЕНЕЖНЫЙ ОБОРОТ page
  • counterparties.py — КОНТРАГЕНТЫ page
  • utils.py          — shared helpers (calculate_change, DB accessors, etc.)

This file re-exports every @frappe.whitelist() function so that
the old JS paths  armada.armada_custom_app.api.dashboard.<fn>  keep working
without any frontend changes.
"""

# ── ГЛАВНАЯ ─────────────────────────────────────────────────────────────────────────
from armada.armada_custom_app.api.main import (          # noqa: F401
	get_main_kpis,
	get_yearly_sales,
	get_turnover_data,
	get_production_data,
)

# ── ПРОДАЖИ ─────────────────────────────────────────────────────────────────────────
from armada.armada_custom_app.api.sales import (         # noqa: F401
	get_sales_filter_options,
	get_sales_kpis,
	get_sales_dynamics,
	get_product_ranking,
	get_sales_data,
	get_purchases_kpis,
	get_purchase_data,
	get_supplier_ranking,
)

# ── ДЕНЕЖНЫЙ ОБОРОТ ─────────────────────────────────────────────────────────────────
from armada.armada_custom_app.api.cashflow import (      # noqa: F401
	get_cashflow_filter_options,
	get_cashflow_kpis,
	get_income_expense_data,
	get_income_ranking,
	get_expense_ranking,
	get_cashflow_data,
	get_turnover_summary,
	get_party_cashflow_detail,
	get_pl_expenses,
	get_account_gl_detail,
)

# ── КОНТРАГЕНТЫ ─────────────────────────────────────────────────────────────────────
from armada.armada_custom_app.api.counterparties import ( # noqa: F401
	get_counterparties_kpis,
	get_customer_debts,
	get_supplier_debts,
)

# ── СКЛАД ──────────────────────────────────────────────────────────────────────────
from armada.armada_custom_app.api.warehouse import (  # noqa: F401
	get_warehouse_filter_options,
	get_warehouse_kpis,
	get_warehouse_summary,
	get_warehouse_stock_data,
)

# ── БАЛАНС ──────────────────────────────────────────────────────────────────────────
import frappe
from frappe.utils import flt
from datetime import datetime


@frappe.whitelist()
def get_balance_data(year=None):
	"""Get balance sheet data — placeholder (custom DocType removed)."""
	return []


@frappe.whitelist()
def get_balance_kpis():
	"""Balance-sheet KPIs — placeholder (custom DocType removed)."""
	return {
		"total_assets": 0,
		"total_liabilities": 0,
		"working_capital": 0,
		"current_ratio": 0,
		"quick_ratio": 0,
		"cash_ratio": 0,
		"financial_leverage": 0,
	}
