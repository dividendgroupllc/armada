"""
Party Balance Grouped — Full Balance Sheet Replacement
=======================================================
ERPNext v15 | Armada Custom App
Production-ready version v2 — sign-split logic.

CORE LOGIC:
  1310 (Receivable / Debitorka account):
      net >= 0  → DEBITORKA > Customers   (ular bizdan qarz)
      net <  0  → CREDITORKA > Customers  (biz qarzMIZ, abs qiymat)

  2110 (Payable / Creditorka account):
      net <= 0  → CREDITORKA > Suppliers  (biz qarzMIZ, abs qiymat)
      net >  0  → DEBITORKA > Suppliers   (ular bizdan qarz)

TREE STRUCTURE:
  Debitorka (1310 row)
    ├─ Customers  [is_group]
    │    ├─ Customer Group A  [is_group]
    │    │    ├─ Customer 1   [leaf]
    │    │    └─ Customer 2   [leaf]
    │    └─ Customer Group B  [is_group]
    │         └─ Customer 3   [leaf]
    └─ Suppliers  [is_group]  ← 2110 dan ko'chirilgan, net>0 bo'lganlar
         ├─ Supplier Group X  [is_group]
         │    └─ Supplier A   [leaf]  +20$
         └─ Supplier Group Y  [is_group]
              └─ Supplier B   [leaf]  +30$

  Creditorka (2110 row)
    ├─ Suppliers  [is_group]
    │    ├─ Supplier Group X  [is_group]
    │    │    └─ Supplier C   [leaf]  +180$
    │    └─ ...               total   +350$
    └─ Customers  [is_group]  ← 1310 dan ko'chirilgan, net<0 bo'lganlar
         └─ Customer Group Z  [is_group]
              └─ Customer K   [leaf]  +70$

BALANCE: har bir party faqat BITTA joyda ko'rinadi. Abs qiymat ishlatiladi.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, cstr
from erpnext.accounts.report.financial_statements import (
    get_data,
    get_columns,
    get_period_list,
    get_fiscal_year_data,
)

# Tree node separator — account/party nomida uchramaydigan unicode belgi
SEP = "\u00a7\u00a7"   # §§


# ═══════════════════════════════════════════════════════════════════════════════
# DYNAMIC PARTY ACCOUNTS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_party_accounts(company):
    """
    Returns:
        receivable_accs : list[str]  — Receivable account names
        payable_accs    : list[str]  — Payable account names
    """
    rows = frappe.db.get_all(
        "Account",
        filters={
            "company":      company,
            "account_type": ["in", ["Receivable", "Payable"]],
            "disabled":     0,
            "is_group":     0,
        },
        fields=["name", "account_type"],
    )

    if not rows:
        frappe.msgprint(
            _("No Receivable or Payable accounts found for company {0}").format(company),
            indicator="orange",
            alert=True,
        )

    receivable_accs = [r.name for r in rows if r.account_type == "Receivable"]
    payable_accs    = [r.name for r in rows if r.account_type == "Payable"]
    return receivable_accs, payable_accs


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    receivable_accs, payable_accs = _get_party_accounts(filters.company)
    all_party_accs = receivable_accs + payable_accs

    if not all_party_accs:
        return [], []

    period_list = get_period_list(
        filters.from_fiscal_year,
        filters.to_fiscal_year,
        filters.period_start_date,
        filters.period_end_date,
        filters.filter_based_on,
        filters.periodicity,
        company=filters.company,
    )

    if not period_list:
        frappe.throw(_("No periods found for the selected date range / fiscal year."))

    if filters.filter_based_on == "Fiscal Year":
        filters.period_start_date = period_list[0]["year_start_date"]

    accumulated = _cint(filters.get("accumulated_values", 1))

    # ── Standard Balance Sheet rows from ERPNext ─────────────────────────────
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

    # ── Raw GL: {account: {party: {period_key: net, "total": net}}} ──────────
    raw_gl = _fetch_party_gl(filters, period_list, all_party_accs, accumulated)

    # ── Party group lookup (2 SQL queries total) ──────────────────────────────
    group_map = _build_group_map(raw_gl, receivable_accs, payable_accs)

    # ── Split into 4 sign-based buckets ──────────────────────────────────────
    buckets = _split_to_buckets(raw_gl, receivable_accs, payable_accs, period_list)

    currency = frappe.db.get_value("Company", filters.company, "default_currency")

    # ── Inject into Balance Sheet sections ───────────────────────────────────
    asset_rows = _inject_section(
        asset_data, receivable_accs, payable_accs,
        buckets, group_map, period_list, filters, currency,
        target="debitorka",
    )
    liability_rows = _inject_section(
        liability_data, receivable_accs, payable_accs,
        buckets, group_map, period_list, filters, currency,
        target="creditorka",
    )
    equity_rows = _inject_section(
        equity_data, receivable_accs, payable_accs,
        buckets, group_map, period_list, filters, currency,
        target=None,
    )

    data    = asset_rows + [{}] + liability_rows + [{}] + equity_rows
    columns = get_columns(
        filters.periodicity, period_list, accumulated,
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

def _fetch_party_gl(filters, period_list, all_party_accs, accumulated):
    """
    Fetches opening + period GL.
    Returns: {account: {party: {period_key: net, "total": net, "opening": net}}}
    net = debit - credit (raw, no sign adjustment — done at split stage)
    """
    if not all_party_accs:
        return {}

    cost_centers = filters.get("cost_center") or []
    cc_clause    = "AND gle.cost_center IN %(cc)s" if cost_centers else ""

    finance_book = (
        filters.get("finance_book")
        or frappe.db.get_value("Company", filters.company, "default_finance_book")
    )
    if filters.get("include_default_book_entries"):
        fb_clause = (
            "AND (gle.finance_book = %(fb)s"
            " OR gle.finance_book IS NULL"
            " OR gle.finance_book = '')"
        )
    else:
        fb_clause = "AND (gle.finance_book IS NULL OR gle.finance_book = '')"

    base_params = {
        "co": filters.company,
        "ac": all_party_accs,
        "fb": finance_book,
    }
    if cost_centers:
        base_params["cc"] = cost_centers

    # Opening balance (before period start)
    opening_rows = frappe.db.sql(
        f"""
        SELECT
            gle.account,
            gle.party,
            SUM(gle.debit)  AS d,
            SUM(gle.credit) AS c
        FROM   `tabGL Entry` gle
        WHERE  gle.company       = %(co)s
          AND  gle.docstatus    != 2
          AND  gle.posting_date  < %(sd)s
          AND  gle.account       IN %(ac)s
          AND  gle.party IS NOT NULL
          AND  gle.party != ''
          {cc_clause}
          {fb_clause}
        GROUP BY gle.account, gle.party
        """,
        {**base_params, "sd": filters.period_start_date},
        as_dict=True,
    )

    # Period entries — aggregated by date (no raw row scan)
    period_rows = frappe.db.sql(
        f"""
        SELECT
            gle.account,
            gle.party,
            DATE(gle.posting_date) AS posting_date,
            SUM(gle.debit)         AS debit,
            SUM(gle.credit)        AS credit
        FROM   `tabGL Entry` gle
        WHERE  gle.company       = %(co)s
          AND  gle.docstatus    != 2
          AND  gle.posting_date  BETWEEN %(sd)s AND %(ed)s
          AND  gle.account       IN %(ac)s
          AND  gle.party IS NOT NULL
          AND  gle.party != ''
          {cc_clause}
          {fb_clause}
        GROUP BY gle.account, gle.party, DATE(gle.posting_date)
        """,
        {**base_params,
         "sd": filters.period_start_date,
         "ed": filters.period_end_date},
        as_dict=True,
    )

    # Period key lookup
    pmap = [
        {"key": p.key, "from": getdate(p.from_date), "to": getdate(p.to_date)}
        for p in period_list
    ]
    first_key = period_list[0].key if period_list else None

    def _pkey(dt):
        d = getdate(dt)
        for p in pmap:
            if p["from"] <= d <= p["to"]:
                return p["key"]
        return None

    result = {a: {} for a in all_party_accs}

    def _ensure(acc, party):
        if party not in result[acc]:
            result[acc][party] = {p.key: 0.0 for p in period_list}
            result[acc][party]["total"]   = 0.0
            result[acc][party]["opening"] = 0.0

    # Seed opening
    for row in opening_rows:
        acc, party = row.account, row.party
        if acc not in result:
            continue
        _ensure(acc, party)
        net = flt(row.d) - flt(row.c)
        result[acc][party]["opening"] += net
        result[acc][party]["total"]   += net
        if accumulated and first_key:
            result[acc][party][first_key] += net

    # Seed period
    for row in period_rows:
        acc, party = row.account, row.party
        if acc not in result:
            continue
        _ensure(acc, party)
        pk  = _pkey(row.posting_date)
        net = flt(row.debit) - flt(row.credit)
        if pk:
            result[acc][party][pk]      += net
            result[acc][party]["total"] += net
        else:
            frappe.log_error(
                title="Party Balance Grouped: GL date outside period range",
                message=(
                    f"GL Entry date {row.posting_date} for account {acc} / "
                    f"party {party} does not fall within any period. Skipped."
                ),
            )

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP MAP — 2 SQL queries total
# ═══════════════════════════════════════════════════════════════════════════════

def _build_group_map(raw_gl, receivable_accs, payable_accs):
    """
    Returns {party_name: group_name} for all parties across all accounts.
    Customers: fetched from tabCustomer.customer_group
    Suppliers: fetched from tabSupplier.supplier_group
    """
    customer_names = set()
    supplier_names = set()

    for acc, party_map in raw_gl.items():
        if acc in receivable_accs:
            customer_names.update(party_map.keys())
        elif acc in payable_accs:
            supplier_names.update(party_map.keys())

    result = {}

    if customer_names:
        rows = frappe.db.sql(
            "SELECT name, customer_group g FROM `tabCustomer` WHERE name IN %(n)s",
            {"n": list(customer_names)},
            as_dict=True,
        )
        for r in rows:
            result[r.name] = r.g or _("Ungrouped")

    if supplier_names:
        rows = frappe.db.sql(
            "SELECT name, supplier_group g FROM `tabSupplier` WHERE name IN %(n)s",
            {"n": list(supplier_names)},
            as_dict=True,
        )
        for r in rows:
            result[r.name] = r.g or _("Ungrouped")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SIGN-SPLIT → 4 BUCKETS
# ═══════════════════════════════════════════════════════════════════════════════

def _split_to_buckets(raw_gl, receivable_accs, payable_accs, period_list):
    """
    Splits each party's raw net balance into one of 4 FLAT buckets.

    Receivable account (1310), raw net = debit - credit:
        net >= 0  -> debtor_customers    (they owe us -> Debitorka/Customers)
        net <  0  -> creditor_customers  (we owe them -> Creditorka/Customers, abs)

    Payable account (2110), raw net = debit - credit:
        net <= 0  -> creditor_suppliers  (we owe them -> Creditorka/Suppliers, abs)
        net >  0  -> debtor_suppliers    (they owe us -> Debitorka/Suppliers)

    CRITICAL FIX: Buckets are FLAT keyed by party name only — NOT by account.
    Previous bug: bucket stored as {acc: {party: data}} but inject looked up
    by receivable/payable acc respectively, causing cross-account lookup to
    always return empty dict and suppliers/customers never showing on wrong side.

    Flat storage eliminates the acc key mismatch entirely.

    Bucket structure:
        { party_name: { period_key: abs_amount, "total": abs_amount } }
    """
    buckets = {
        "debtor_customers":   {},
        "debtor_suppliers":   {},
        "creditor_customers": {},
        "creditor_suppliers": {},
    }

    def _add(bucket, party, pdata, negate):
        if party not in bucket:
            bucket[party] = {p.key: 0.0 for p in period_list}
            bucket[party]["total"] = 0.0
        factor = -1.0 if negate else 1.0
        for p in period_list:
            bucket[party][p.key] += flt(pdata.get(p.key, 0)) * factor
        bucket[party]["total"] += flt(pdata.get("total", 0)) * factor

    for acc, party_map in raw_gl.items():
        is_receivable = acc in receivable_accs
        is_payable    = acc in payable_accs

        for party, pdata in party_map.items():
            total = flt(pdata.get("total", 0))

            if is_receivable:
                if total >= 0:
                    _add(buckets["debtor_customers"], party, pdata, negate=False)
                else:
                    _add(buckets["creditor_customers"], party, pdata, negate=True)

            elif is_payable:
                if total <= 0:
                    _add(buckets["creditor_suppliers"], party, pdata, negate=True)
                else:
                    _add(buckets["debtor_suppliers"], party, pdata, negate=False)

    return buckets


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION INJECT
# ═══════════════════════════════════════════════════════════════════════════════

def _inject_section(
    section_rows, receivable_accs, payable_accs,
    buckets, group_map, period_list, filters, currency,
    target,
):
    """
    Walks one Balance Sheet section (Asset / Liability / Equity).
    When a party account is found, injects the appropriate buckets.

    target="debitorka":
        receivable account row → emit Customers block + Suppliers block
    target="creditorka":
        payable account row   → emit Suppliers block + Customers block
    target=None:
        pass-through (Equity)
    """
    show_zero = _cint(filters.get("show_zero_balance", 1))
    out = []

    for row in section_rows:
        out.append(row)

        if target is None:
            continue

        acc         = cstr(row.get("account") or "")
        base_indent = flt(row.get("indent", 0))

        if target == "debitorka" and acc in receivable_accs:
            _emit_block(
                out, acc, base_indent,
                bucket_data  = buckets["debtor_customers"],
                block_label  = _("Customers"),
                block_prefix = "cust",
                group_map    = group_map,
                period_list  = period_list,
                show_zero    = show_zero,
                currency     = currency,
            )
            _emit_block(
                out, acc, base_indent,
                bucket_data  = buckets["debtor_suppliers"],
                block_label  = _("Suppliers"),
                block_prefix = "sup",
                group_map    = group_map,
                period_list  = period_list,
                show_zero    = show_zero,
                currency     = currency,
            )

        elif target == "creditorka" and acc in payable_accs:
            _emit_block(
                out, acc, base_indent,
                bucket_data  = buckets["creditor_suppliers"],
                block_label  = _("Suppliers"),
                block_prefix = "sup",
                group_map    = group_map,
                period_list  = period_list,
                show_zero    = show_zero,
                currency     = currency,
            )
            _emit_block(
                out, acc, base_indent,
                bucket_data  = buckets["creditor_customers"],
                block_label  = _("Customers"),
                block_prefix = "cust",
                group_map    = group_map,
                period_list  = period_list,
                show_zero    = show_zero,
                currency     = currency,
            )

    return out


def _emit_block(
    out, acc, base_indent,
    bucket_data, block_label, block_prefix,
    group_map, period_list, show_zero, currency,
):
    """
    Emits one party-type block under a balance sheet account row.
    Tree depth relative to base_indent:
        +1  block     (Customers / Suppliers)      is_group=1
        +2  group     (Customer Group / Sup Group)  is_group=1
        +3  party     (individual party name)       is_group=0
    """
    if not bucket_data:
        return

    # ── Aggregate into groups ────────────────────────────────────────────────
    groups = {}
    for party, pdata in bucket_data.items():
        grp = group_map.get(party, _("Ungrouped"))

        if grp not in groups:
            groups[grp] = {p.key: 0.0 for p in period_list}
            groups[grp]["total"]   = 0.0
            groups[grp]["parties"] = {}

        for p in period_list:
            groups[grp][p.key] += flt(pdata.get(p.key, 0))
        groups[grp]["total"] += flt(pdata.get("total", 0))

        groups[grp]["parties"][party] = {p.key: flt(pdata.get(p.key, 0)) for p in period_list}
        groups[grp]["parties"][party]["total"] = flt(pdata.get("total", 0))

    # ── Block-level totals ────────────────────────────────────────────────────
    block_total = sum(flt(gd["total"]) for gd in groups.values())
    block_pvals = {p.key: sum(flt(gd.get(p.key, 0)) for gd in groups.values())
                   for p in period_list}

    if (not show_zero
            and block_total == 0
            and all(block_pvals.get(p.key, 0) == 0 for p in period_list)):
        return

    # Block row  (depth +1)
    block_key = f"{acc}{SEP}{block_prefix}"
    block_row = frappe._dict({
        "account":        block_key,
        "account_name":   block_label,
        "parent_account": acc,
        "indent":         base_indent + 1,
        "is_group":       1,
        "has_value":      True,
        "currency":       currency,
        "total":          block_total,
    })
    for p in period_list:
        block_row[p.key] = block_pvals.get(p.key, 0.0)
    out.append(block_row)

    # ── Group rows (depth +2) ────────────────────────────────────────────────
    for grp_name in sorted(groups.keys()):
        gd = groups[grp_name]

        if (not show_zero
                and flt(gd["total"]) == 0
                and all(flt(gd.get(p.key, 0)) == 0 for p in period_list)):
            continue

        grp_key = f"{block_key}{SEP}{grp_name}"
        grp_row = frappe._dict({
            "account":        grp_key,
            "account_name":   grp_name,
            "parent_account": block_key,
            "indent":         base_indent + 2,
            "is_group":       1,
            "has_value":      True,
            "currency":       currency,
            "total":          flt(gd["total"]),
        })
        for p in period_list:
            grp_row[p.key] = flt(gd.get(p.key, 0))
        out.append(grp_row)

        # ── Party leaf rows (depth +3) ────────────────────────────────────────
        for party_name in sorted(gd["parties"].keys()):
            pd = gd["parties"][party_name]

            if (not show_zero
                    and flt(pd.get("total", 0)) == 0
                    and all(flt(pd.get(p.key, 0)) == 0 for p in period_list)):
                continue

            leaf = frappe._dict({
                "account":        f"{grp_key}{SEP}{party_name}",
                "account_name":   party_name,
                "parent_account": grp_key,
                "indent":         base_indent + 3,
                "is_group":       0,
                "has_value":      True,
                "currency":       currency,
                "total":          flt(pd.get("total", 0)),
            })
            for p in period_list:
                leaf[p.key] = flt(pd.get(p.key, 0))
            out.append(leaf)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════════════

def _cint(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
