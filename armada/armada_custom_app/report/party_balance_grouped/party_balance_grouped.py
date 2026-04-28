"""
Party Balance Grouped — Full Balance Sheet Replacement
=======================================================
ERPNext v15 | Armada Custom App

Import path (v15 confirmed):
  from erpnext.accounts.report.financial_statements import get_data, get_columns, get_period_list

get_data() signature (v15):
  get_data(company, root_type, balance_must_be, period_list,
           only_current_fiscal_year, filters, accumulated_values)

  root_type       : "Asset" | "Liability" | "Equity"
  balance_must_be : "Debit"  (Asset) | "Credit" (Liability/Equity)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate
from erpnext.accounts.report.financial_statements import (
    get_data,
    get_columns,
    get_period_list,
    get_fiscal_year_data,
)

# ── Party accounts — Chart of Accounts'dagi ANIQ nomga moslashtiring ────────
# sign:  +1 = debit-normal (asset)    balance = debit - credit
#        -1 = credit-normal (liability) balance = credit - debit (positive = owes)
PARTY_ACCOUNTS = {
    "1310 - Debtors - AM":            {"party_type": "Customer", "sign":  1},
    "1312 - Creditors clients - AM":  {"party_type": "Customer", "sign":  1},
    "2110 - Creditors - AM":          {"party_type": "Supplier", "sign": -1},
    "2111 - Debtors supplier - AM":   {"party_type": "Supplier", "sign": -1},
}


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    period_list = get_period_list(
        filters.from_fiscal_year,
        filters.to_fiscal_year,
        filters.period_start_date,
        filters.period_end_date,
        filters.filter_based_on,
        filters.periodicity,
        company=filters.company,
    )

    # v15 balance_sheet.py sets this
    filters.period_start_date = period_list[0]["year_start_date"]

    accumulated = filters.get("accumulated_values", 1)

    # ── Standard Balance Sheet data via ERPNext get_data() ──────────────────
    asset_data = get_data(
        filters.company, "Asset", "Debit", period_list,
        only_current_fiscal_year=False,
        filters=filters,
        accumulated_values=accumulated,
    ) or []

    liability_data = get_data(
        filters.company, "Liability", "Credit", period_list,
        only_current_fiscal_year=False,
        filters=filters,
        accumulated_values=accumulated,
    ) or []

    equity_data = get_data(
        filters.company, "Equity", "Credit", period_list,
        only_current_fiscal_year=False,
        filters=filters,
        accumulated_values=accumulated,
    ) or []

    # ── GL party balances ───────────────────────────────────────────────────
    party_gl = _fetch_party_gl(filters, period_list)

    # ── Inject party tree into each section ────────────────────────────────
    asset_rows     = _inject_party_tree(asset_data,     party_gl, period_list, filters)
    liability_rows = _inject_party_tree(liability_data, party_gl, period_list, filters)
    equity_rows    = _inject_party_tree(equity_data,    party_gl, period_list, filters)

    data = asset_rows + [{}] + liability_rows + [{}] + equity_rows

    # ── Columns (ERPNext standart) ──────────────────────────────────────────
    columns = get_columns(
        filters.periodicity,
        period_list,
        accumulated,
        company=filters.company,
    )

    return columns, data


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
def _validate_filters(filters):
    if not filters.company:
        frappe.throw(_("Company is required"))

    if filters.filter_based_on == "Fiscal Year":
        if not filters.from_fiscal_year or not filters.to_fiscal_year:
            frappe.throw(_("Fiscal Year (Start and End) are required"))
        fy = get_fiscal_year_data(filters.from_fiscal_year, filters.to_fiscal_year)
        filters.period_start_date = fy.year_start_date
        filters.period_end_date   = fy.year_end_date
    else:
        if not filters.period_start_date or not filters.period_end_date:
            frappe.throw(_("Start Date and End Date are required"))
        if getdate(filters.period_start_date) > getdate(filters.period_end_date):
            frappe.throw(_("Start Date cannot be after End Date"))


# ═══════════════════════════════════════════════════════════════════════════════
# PARTY GL FETCH
# ═══════════════════════════════════════════════════════════════════════════════
def _fetch_party_gl(filters, period_list):
    """
    Returns:
      { account_name: { party: { period_key: net, "total": net } } }
    net = debit - credit (raw, sign applied at display)
    """
    accs = list(PARTY_ACCOUNTS.keys())
    if not accs:
        return {}

    # Opening balance (before period start) → seeded into first period
    opening = frappe.db.sql(
        """
        SELECT account, party,
               SUM(debit) AS d, SUM(credit) AS c
        FROM   `tabGL Entry`
        WHERE  company      = %(co)s
          AND  posting_date < %(sd)s
          AND  account      IN %(ac)s
          AND  is_cancelled = 0
          AND  party IS NOT NULL AND party != ''
        GROUP  BY account, party
        """,
        {"co": filters.company, "sd": filters.period_start_date, "ac": accs},
        as_dict=True,
    )

    # Period entries
    period_entries = frappe.db.sql(
        """
        SELECT account, party, posting_date, debit, credit
        FROM   `tabGL Entry`
        WHERE  company      = %(co)s
          AND  posting_date BETWEEN %(sd)s AND %(ed)s
          AND  account      IN %(ac)s
          AND  is_cancelled = 0
          AND  party IS NOT NULL AND party != ''
        ORDER  BY posting_date
        """,
        {"co": filters.company,
         "sd": filters.period_start_date,
         "ed": filters.period_end_date,
         "ac": accs},
        as_dict=True,
    )

    # Period key lookup
    pmap = [{"key": p.key, "from": getdate(p.from_date), "to": getdate(p.to_date)}
            for p in period_list]

    def _pkey(dt):
        d = getdate(dt)
        for p in pmap:
            if p["from"] <= d <= p["to"]:
                return p["key"]
        return None

    result = {a: {} for a in accs}

    def _ensure(acc, party):
        if party not in result[acc]:
            result[acc][party] = {p.key: 0.0 for p in period_list}
            result[acc][party]["total"] = 0.0

    first_key = period_list[0].key if period_list else None

    for row in opening:
        acc, party = row.account, row.party
        if acc not in result:
            continue
        _ensure(acc, party)
        net = flt(row.d) - flt(row.c)
        if first_key:
            result[acc][party][first_key] += net
            result[acc][party]["total"]   += net

    for row in period_entries:
        acc, party = row.account, row.party
        if acc not in result:
            continue
        _ensure(acc, party)
        pk  = _pkey(row.posting_date)
        net = flt(row.debit) - flt(row.credit)
        if pk:
            result[acc][party][pk]      += net
            result[acc][party]["total"] += net

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PARTY GROUP META
# ═══════════════════════════════════════════════════════════════════════════════
def _party_group_map(party_type, names):
    if not names:
        return {}
    if party_type == "Customer":
        rows = frappe.db.sql(
            "SELECT name, customer_group g FROM `tabCustomer` WHERE name IN %(n)s",
            {"n": list(names)}, as_dict=True)
    else:
        rows = frappe.db.sql(
            "SELECT name, supplier_group g FROM `tabSupplier` WHERE name IN %(n)s",
            {"n": list(names)}, as_dict=True)
    return {r.name: (r.g or _("Ungrouped")) for r in rows}


# ═══════════════════════════════════════════════════════════════════════════════
# TREE INJECT
# ═══════════════════════════════════════════════════════════════════════════════
def _inject_party_tree(section_rows, party_gl, period_list, filters):
    """
    For every row whose `account` key is in PARTY_ACCOUNTS,
    inject group → individual party rows immediately after it.
    All other rows pass through unchanged.
    """
    show_zero = filters.get("show_zero_balance", 1)
    out = []

    for row in section_rows:
        out.append(row)

        # account key — ERPNext uses `account` field as the unique row id
        acc = row.get("account") or ""

        if acc not in PARTY_ACCOUNTS:
            continue

        meta      = PARTY_ACCOUNTS[acc]
        sign      = meta["sign"]
        pty_type  = meta["party_type"]
        party_bal = party_gl.get(acc, {})
        if not party_bal:
            continue

        group_map = _party_group_map(pty_type, party_bal.keys())
        base_indent = flt(row.get("indent", 0))

        # Aggregate by group
        groups = {}
        for party, pdata in party_bal.items():
            grp = group_map.get(party, _("Ungrouped"))
            if grp not in groups:
                groups[grp] = {p.key: 0.0 for p in period_list}
                groups[grp]["total"]   = 0.0
                groups[grp]["parties"] = {}
            for p in period_list:
                v = flt(pdata.get(p.key, 0)) * sign
                groups[grp][p.key] += v
            groups[grp]["total"] += flt(pdata.get("total", 0)) * sign
            groups[grp]["parties"][party] = {
                p.key: flt(pdata.get(p.key, 0)) * sign for p in period_list
            }
            groups[grp]["parties"][party]["total"] = flt(pdata.get("total", 0)) * sign

        for grp_name in sorted(groups.keys()):
            gd = groups[grp_name]

            if not show_zero and gd["total"] == 0:
                if all(gd.get(p.key, 0) == 0 for p in period_list):
                    continue

            # Unique account key for tree linkage
            grp_key = f"{acc}::{grp_name}"

            grp_row = frappe._dict({
                "account":        grp_key,
                "account_name":   grp_name,
                "parent_account": acc,
                "indent":         base_indent + 1,
                "is_group":       1,
                "has_value":      True,
                "total":          flt(gd["total"]),
            })
            for p in period_list:
                grp_row[p.key] = flt(gd.get(p.key, 0))
            out.append(grp_row)

            for party_name in sorted(gd["parties"].keys()):
                pd = gd["parties"][party_name]

                if not show_zero and pd.get("total", 0) == 0:
                    if all(pd.get(p.key, 0) == 0 for p in period_list):
                        continue

                leaf = frappe._dict({
                    "account":        f"{grp_key}::{party_name}",
                    "account_name":   party_name,
                    "parent_account": grp_key,
                    "indent":         base_indent + 2,
                    "is_group":       0,
                    "has_value":      True,
                    "total":          flt(pd.get("total", 0)),
                })
                for p in period_list:
                    leaf[p.key] = flt(pd.get(p.key, 0))
                out.append(leaf)

    return out
