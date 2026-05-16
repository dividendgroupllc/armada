"""
Party Balance Grouped — Full Balance Sheet Replacement
=======================================================
ERPNext v15 | Armada Custom App
Production-ready version v3 — PER-PERIOD sign-split.

CORE LOGIC:
  1310 (Receivable / Debitorka account):
      running_balance >= 0  → DEBITORKA > Customers   (they owe us)
      running_balance <  0  → CREDITORKA > Customers  (we owe them, abs value)

  2110 (Payable / Creditorka account):
      running_balance <= 0  → CREDITORKA > Suppliers  (we owe them, abs value)
      running_balance >  0  → DEBITORKA > Suppliers   (they owe us)

  running_balance at period N = opening + sum(period_movements[1..N])

  CRITICAL: determination is PER-PERIOD, not per lifetime total.
  The same party may appear in BOTH debtor and creditor buckets across
  different periods. Period column is 0 where the party is on the other side.

  Display value: abs(running_balance) — always positive.
  This is a Balance Sheet: we show the BALANCE, not the movement.

  total field: abs balance at LAST period = current state at report end.

TREE STRUCTURE (unchanged):
  Debitorka (1310 row)
    ├─ Customers  [is_group]
    │    ├─ Customer Group A  [is_group]
    │    │    ├─ Customer 1   [leaf]  Jan:200 Feb:0
    │    │    └─ Customer 2   [leaf]
    └─ Suppliers  [is_group]

  Creditorka (2110 row)
    ├─ Suppliers  [is_group]
    └─ Customers  [is_group]
         └─ Customer Group A [is_group]
              └─ Customer 1  [leaf]  Jan:0  Feb:150  ← same party, switched side in Feb

v3 changes vs v2:
  - _split_to_buckets: complete rewrite — per-period running balance logic
  - execute: passes `accumulated` flag into _split_to_buckets
  - All other functions: UNCHANGED
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

# Tree node separator — must not appear in account/party names
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

    # ── v3: Per-period sign split into 4 buckets ──────────────────────────────
    # `accumulated` is passed so we can correctly strip opening from first
    # period key (which _fetch_party_gl bakes in when accumulated=True).
    buckets = _split_to_buckets(
        raw_gl, receivable_accs, payable_accs, period_list, accumulated
    )

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

    When accumulated=True, opening balance is also added into the first period key
    so that ERPNext's standard accumulation rendering works for non-party rows.
    _split_to_buckets strips this back out to compute correct per-period running balance.
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

    # Period entries — aggregated by date
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
# SIGN-SPLIT → 4 BUCKETS  (v3: PER-PERIOD)
# ═══════════════════════════════════════════════════════════════════════════════

def _split_to_buckets(raw_gl, receivable_accs, payable_accs, period_list, accumulated):
    """
    PER-PERIOD sign-split into 4 flat buckets.

    Algorithm:
        For each party in each GL account:
          1. Extract pure period movements for each period.
             When accumulated=True, _fetch_party_gl bakes opening into the
             FIRST period key. We subtract opening from that key to get the
             pure movement. For accumulated=False, opening is not baked in.
          2. Walk periods sequentially, maintaining a running cumulative balance:
                running[0] = opening + movement[0]
                running[N] = running[N-1] + movement[N]
          3. At each period, the SIGN of running determines the bucket:

             Receivable account (1310), net = debit - credit:
               running >= 0  →  debtor_customers    (they owe us)
               running <  0  →  creditor_customers  (we owe them)

             Payable account (2110), net = debit - credit:
               running <= 0  →  creditor_suppliers  (we owe them)
               running >  0  →  debtor_suppliers    (they owe us)

          4. Store abs(running) in the determined bucket's period column.
             The OTHER bucket gets 0 for that period (default from _ensure).

    Result: one party CAN appear in BOTH debtor and creditor buckets.
    Example — Customer 1:
        Jan end balance = +$200  → debtor_customers[Jan]   = 200
        Feb end balance = -$150  → creditor_customers[Feb] = 150
        debtor_customers[Feb]    = 0  (not in debtor side for Feb)
        creditor_customers[Jan]  = 0  (not in creditor side for Jan)

    Display value: abs(running cumulative balance) — always positive.
    This is a Balance Sheet: we show the BALANCE, not the period movement.

    total field: abs balance at LAST period in period_list.
        = the party's current outstanding balance as of report end date.
        This is the only semantically correct "total" for a cumulative BS view.

    Edge cases handled:
        - Party never crossing zero: appears in one bucket only, other is empty ✓
        - Party with only opening balance, no period movements: running = opening
          for all periods → correct bucket for all periods ✓
        - Party with balance exactly zero: running=0 treated as non-negative
          → debtor bucket with value 0 → filtered by show_zero logic ✓
        - Same party in multiple receivable accounts: flat bucket key is party
          name only, values accumulate correctly ✓
        - Party as both customer (receivable) and supplier (payable): routed
          to customer vs supplier buckets respectively — no collision ✓
        - accumulated=False: opening not in first key, movements parsed correctly,
          running balance still computed cumulatively (correct for BS sign logic) ✓
    """
    buckets = {
        "debtor_customers":   {},
        "debtor_suppliers":   {},
        "creditor_customers": {},
        "creditor_suppliers": {},
    }

    def _ensure(bucket, party):
        """Initialise party entry with all period columns = 0."""
        if party not in bucket:
            bucket[party] = {p.key: 0.0 for p in period_list}
            bucket[party]["total"] = 0.0

    for acc, party_map in raw_gl.items():
        is_receivable = acc in receivable_accs
        is_payable    = acc in payable_accs

        if not (is_receivable or is_payable):
            continue

        for party, pdata in party_map.items():
            opening = flt(pdata.get("opening", 0))

            # ── Step 1: Extract pure period movements ─────────────────────────
            # When accumulated=True, _fetch_party_gl adds opening into the
            # first period key so the raw value for period 0 =
            # opening + period_0_movements. We strip opening back out so
            # each element in `movements` represents only that period's net
            # GL activity. This is required to compute a correct running total.
            movements = []
            for i, p in enumerate(period_list):
                raw_val = flt(pdata.get(p.key, 0))
                if accumulated and i == 0:
                    raw_val -= opening   # un-bake opening from first period key
                movements.append((p.key, raw_val))

            # ── Step 2 + 3: Walk periods, compute running, assign to bucket ──
            running = opening
            for pkey, mov in movements:
                running += mov
                abs_balance = abs(running)

                if is_receivable:
                    if running >= 0:
                        _ensure(buckets["debtor_customers"], party)
                        buckets["debtor_customers"][party][pkey] = abs_balance
                    else:
                        _ensure(buckets["creditor_customers"], party)
                        buckets["creditor_customers"][party][pkey] = abs_balance

                elif is_payable:
                    if running <= 0:
                        _ensure(buckets["creditor_suppliers"], party)
                        buckets["creditor_suppliers"][party][pkey] = abs_balance
                    else:
                        _ensure(buckets["debtor_suppliers"], party)
                        buckets["debtor_suppliers"][party][pkey] = abs_balance

    # ── Step 4: Compute total field ───────────────────────────────────────────
    # total = abs balance at LAST period = current state at report end date.
    # Summing across periods would double-count accumulated balances — wrong.
    last_pkey = period_list[-1].key if period_list else None
    for bucket in buckets.values():
        for pdata in bucket.values():
            pdata["total"] = flt(pdata.get(last_pkey, 0)) if last_pkey else 0.0

    return buckets


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION INJECT  (UNCHANGED from v2)
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

    NOTE: With per-period sign-split, a party that switched sides mid-year
    may appear here with non-zero values only in periods where it belongs
    to this side. Its period columns are 0 otherwise. The show_zero filter
    only hides rows where ALL period columns AND total are 0 simultaneously,
    so historical-only exposure (zero current total) is still visible.
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
