"""
Direct Cash Flow Report (ДДС — Движение Денежных Средств)
App     : armada
Module  : armada_custom_app

Data sources  : Payment Entry (primary) + Journal Entry (secondary)
Mapping       : Cash Flow Categories + Cash Flow Categories Item
Performance   : 4 SQL queries max, account_map cached 5 min, no N+1
"""

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from collections import defaultdict
from datetime import date, timedelta
import calendar


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    validate_filters(filters)

    # 1. Build period columns
    periods = get_periods(filters)
    columns = get_columns(periods)

    # 2. Account map (cached)
    account_map = build_account_map()

    # 3. Cash / bank accounts list
    cash_accounts = get_cash_bank_accounts(filters.company)

    # 4. Per-period opening balances from GL Entry
    #    period_openings[period_key] = balance at start of that period
    period_openings = get_period_opening_balances(
        filters.company, filters.from_date, periods, cash_accounts
    )

    # 5. All movements in range — single UNION ALL query
    movements = get_all_movements(filters, cash_accounts)

    # 6. Aggregate into structure
    aggregated, unmapped = aggregate_movements(movements, account_map, periods)

    # 7. Build report rows
    data = build_report_rows(aggregated, account_map, periods, period_openings)

    # 8. Log unmapped for debug (non-blocking)
    if unmapped:
        frappe.log_error(
            title="Direct Cash Flow — Unmapped accounts",
            message="\n".join(
                f"{m.get('voucher_no')} | {m.get('mapping_account')} | {m.get('amount')}"
                for m in unmapped[:50]
            ),
        )

    return columns, data


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From Date and To Date are required"))
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date"))

    display_type = filters.get("display_type", "Monthly")
    if display_type == "Daily":
        delta = (getdate(filters.to_date) - getdate(filters.from_date)).days
        if delta > 90:
            frappe.throw(_("Daily display: maximum range is 90 days"))
    if display_type == "Weekly":
        delta = (getdate(filters.to_date) - getdate(filters.from_date)).days
        if delta > 365:
            frappe.throw(_("Weekly display: maximum range is 365 days"))


# ---------------------------------------------------------------------------
# PERIOD GENERATION
# ---------------------------------------------------------------------------

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def get_periods(filters):
    from_date = getdate(filters.from_date)
    to_date = getdate(filters.to_date)
    display_type = filters.get("display_type", "Monthly")
    periods = []

    if display_type == "Monthly":
        y, m = from_date.year, from_date.month
        while date(y, m, 1) <= to_date:
            last_day = calendar.monthrange(y, m)[1]
            p_start = date(y, m, 1)
            p_end = min(date(y, m, last_day), to_date)
            periods.append({
                "key": f"{y}_{m:02d}",
                "label": f"{MONTH_NAMES_RU[m]} {y}",
                "start": p_start,
                "end": p_end,
            })
            m += 1
            if m > 12:
                m = 1
                y += 1

    elif display_type == "Quarterly":
        y, m = from_date.year, from_date.month
        # Snap to quarter start
        q_start_month = ((m - 1) // 3) * 3 + 1
        current = date(y, q_start_month, 1)
        while current <= to_date:
            q = (current.month - 1) // 3 + 1
            q_end_month = q * 3
            q_end_day = calendar.monthrange(current.year, q_end_month)[1]
            p_end = min(date(current.year, q_end_month, q_end_day), to_date)
            p_start = max(current, from_date)
            periods.append({
                "key": f"{current.year}_Q{q}",
                "label": f"Q{q} {current.year}",
                "start": p_start,
                "end": p_end,
            })
            # Next quarter
            next_month = q_end_month + 1
            if next_month > 12:
                next_month = 1
                current = date(current.year + 1, next_month, 1)
            else:
                current = date(current.year, next_month, 1)

    elif display_type == "Weekly":
        # ISO weeks, Monday start
        current = from_date - timedelta(days=from_date.weekday())
        week_num = 0
        while current <= to_date:
            p_start = max(current, from_date)
            p_end = min(current + timedelta(days=6), to_date)
            week_num += 1
            periods.append({
                "key": f"W{week_num}_{current.strftime('%Y%m%d')}",
                "label": f"{p_start.strftime('%d.%m')} - {p_end.strftime('%d.%m.%Y')}",
                "start": p_start,
                "end": p_end,
            })
            current += timedelta(days=7)

    elif display_type == "Daily":
        current = from_date
        while current <= to_date:
            periods.append({
                "key": current.strftime("%Y%m%d"),
                "label": current.strftime("%d.%m.%Y"),
                "start": current,
                "end": current,
            })
            current += timedelta(days=1)

    return periods


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns(periods):
    columns = [
        {
            "fieldname": "label",
            "label": _("Category"),
            "fieldtype": "Data",
            "width": 250,
        }
    ]
    for p in periods:
        columns.append({
            "fieldname": p["key"],
            "label": p["label"],
            "fieldtype": "Currency",
            "width": 130,
        })
    return columns


# ---------------------------------------------------------------------------
# ACCOUNT MAP  (cached 5 min)
# ---------------------------------------------------------------------------

def build_account_map():
    """
    Returns dict: { account_name: { category_name, activity_type,
                                    is_inflow, sort_order, parent_name,
                                    direction_override } }
    Uses Frappe cache to avoid repeated DB hits.
    """
    cache_key = "direct_cash_flow_account_map_v2"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    parents = frappe.get_all(
        "Cash Flow Categories",
        fields=["name", "category_name", "activity_type", "is_inflow", "sort_order"],
    )
    parent_map = {p["name"]: p for p in parents}

    children = frappe.get_all(
        "Cash Flow Categories Item",
        fields=[
            "parent",
            "direct_expence_account",
            "account_label",
            "direction_override",
        ],
        filters={"parenttype": "Cash Flow Categories"},
    )

    account_map = {}
    for child in children:
        acc = child.get("direct_expence_account")
        if not acc:
            continue
        parent = parent_map.get(child["parent"])
        if not parent:
            continue

        # Determine effective is_inflow
        override = child.get("direction_override") or ""
        if override == "Приход (Inflow)":
            effective_inflow = 1
        elif override == "Расход (Outflow)":
            effective_inflow = 0
        else:
            effective_inflow = cint(parent["is_inflow"])

        display_label = child.get("account_label") or parent["category_name"]

        account_map[acc] = {
            "category_name": parent["category_name"],
            "display_label": display_label,
            "activity_type": parent["activity_type"],
            "is_inflow": effective_inflow,
            "sort_order": cint(parent["sort_order"]),
            "parent_name": parent["name"],
            "direction_override": override,
        }

    frappe.cache().set_value(cache_key, account_map, expires_in_sec=300)
    return account_map


# ---------------------------------------------------------------------------
# CASH / BANK ACCOUNTS
# ---------------------------------------------------------------------------

def get_cash_bank_accounts(company):
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "account_type": ["in", ["Cash", "Bank"]],
            "is_group": 0,
        },
        pluck="name",
    )
    return accounts


# ---------------------------------------------------------------------------
# OPENING BALANCE — PER PERIOD
# ---------------------------------------------------------------------------

def get_period_opening_balances(company, from_date, periods, cash_accounts):
    """
    Returns dict: { period_key: opening_balance_at_start_of_period }

    Logic:
      1. Get cumulative GL net by year-month BEFORE the report's to_date
         (one SQL, grouped by month)
      2. Build running total → opening for each period

    Example:
      Report: Jan 2026 – Mar 2026
      Jan opening = SUM(GL before 2026-01-01)
      Feb opening = SUM(GL before 2026-02-01) = Jan opening + Jan net
      Mar opening = SUM(GL before 2026-03-01) = Feb opening + Feb net
    """
    if not cash_accounts or not periods:
        return {p["key"]: 0.0 for p in periods}

    # Earliest date we need: day before first period start
    first_period_start = periods[0]["start"]
    last_period_end    = periods[-1]["end"]

    # Get all monthly GL net flows up to last period end
    # We fetch from beginning of time up to last period end
    monthly_net = frappe.db.sql(
        """
        SELECT
            YEAR(posting_date)   AS yr,
            MONTH(posting_date)  AS mo,
            SUM(debit - credit)  AS net
        FROM `tabGL Entry`
        WHERE
            account      IN %(accounts)s
            AND company  = %(company)s
            AND posting_date <= %(last_date)s
            AND is_cancelled = 0
        GROUP BY
            YEAR(posting_date),
            MONTH(posting_date)
        ORDER BY yr, mo
        """,
        {
            "accounts":  cash_accounts,
            "company":   company,
            "last_date": last_period_end,
        },
        as_dict=True,
    )

    # Build cumulative balance timeline: {(year, month): cumulative up to END of that month}
    cumulative = {}
    running = 0.0
    for row in monthly_net:
        running += flt(row["net"])
        cumulative[(int(row["yr"]), int(row["mo"]))] = running

    def balance_before_date(d):
        """Sum of all GL net strictly before date d."""
        total = 0.0
        for (yr, mo), cum in cumulative.items():
            last_day_of_month = calendar.monthrange(yr, mo)[1]
            month_end = date(yr, mo, last_day_of_month)
            if month_end < d:
                # This entire month is before d — but we need incremental net
                # Recalculate as sum of months whose END < d
                pass
        # Simpler: sum net of months that end before d
        total = 0.0
        prev_cum = 0.0
        for row in monthly_net:
            yr, mo = int(row["yr"]), int(row["mo"])
            last_day = calendar.monthrange(yr, mo)[1]
            month_end = date(yr, mo, last_day)
            month_net = flt(row["net"])
            if month_end < d:
                total += month_net
        return total

    # Calculate opening for each period
    period_openings = {}
    for p in periods:
        period_openings[p["key"]] = balance_before_date(p["start"])

    return period_openings


# ---------------------------------------------------------------------------
# MOVEMENTS — SINGLE UNION ALL QUERY
# ---------------------------------------------------------------------------

def get_all_movements(filters, cash_accounts):
    """
    Returns unified list of cash movements from both PE and JE.
    Single SQL call — no N+1.
    """
    if not cash_accounts:
        return []

    params = {
        "company": filters.company,
        "from_date": filters.from_date,
        "to_date": filters.to_date,
        "cash_accounts": cash_accounts,
    }

    party_condition = ""
    if filters.get("party_type"):
        party_condition = "AND pe.party_type = %(party_type)s"
        params["party_type"] = filters.party_type

    query = """
        SELECT
            'PE'                            AS source,
            pe.name                         AS voucher_no,
            pe.posting_date,
            pe.payment_type,
            pe.paid_from                    AS account_from,
            pe.paid_to                      AS account_to,
            pe.base_paid_amount             AS amount,
            pe.party_type,
            pe.party
        FROM `tabPayment Entry` pe
        WHERE
            pe.docstatus   = 1
            AND pe.company = %(company)s
            AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND pe.payment_type IN ('Receive', 'Pay')
            {party_condition}

        UNION ALL

        SELECT
            'JE'                            AS source,
            je.name                         AS voucher_no,
            je.posting_date,
            CASE
                WHEN jea_cash.credit > 0 THEN 'Pay'
                ELSE 'Receive'
            END                             AS payment_type,
            jea_counter.account             AS account_from,
            jea_cash.account                AS account_to,
            CASE
                WHEN jea_cash.credit > 0
                    THEN jea_cash.credit_in_account_currency
                ELSE jea_cash.debit_in_account_currency
            END                             AS amount,
            NULL                            AS party_type,
            NULL                            AS party
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea_cash
            ON jea_cash.parent = je.name
            AND jea_cash.account IN %(cash_accounts)s
        INNER JOIN `tabJournal Entry Account` jea_counter
            ON jea_counter.parent = je.name
            AND jea_counter.account NOT IN %(cash_accounts)s
        WHERE
            je.docstatus   = 1
            AND je.company = %(company)s
            AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s
    """.format(
        party_condition=party_condition
    )

    rows = frappe.db.sql(query, params, as_dict=True)
    return rows


# ---------------------------------------------------------------------------
# PERIOD KEY LOOKUP
# ---------------------------------------------------------------------------

def get_period_key(posting_date, periods):
    """Binary-safe O(n) scan — n is small (max ~365 daily periods)."""
    d = getdate(posting_date)
    for p in periods:
        if p["start"] <= d <= p["end"]:
            return p["key"]
    return None


# ---------------------------------------------------------------------------
# AGGREGATION  (pure Python, no extra DB calls)
# ---------------------------------------------------------------------------

def aggregate_movements(movements, account_map, periods):
    """
    structure:
      result[activity_type][parent_name][period_key] += amount
    """
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    unmapped = []

    for m in movements:
        # Determine which account to use for category lookup
        if m["source"] == "PE":
            if m["payment_type"] == "Receive":
                mapping_account = m["account_from"]  # Customer receivable side
            else:
                mapping_account = m["account_to"]    # Supplier/expense side
        else:
            # JE: account_from = counter (non-cash) account
            mapping_account = m["account_from"]

        cat = account_map.get(mapping_account)
        if not cat:
            unmapped.append({
                "voucher_no": m["voucher_no"],
                "mapping_account": mapping_account,
                "amount": m["amount"],
            })
            continue

        period_key = get_period_key(m["posting_date"], periods)
        if not period_key:
            continue

        # Internal transfer guard: skip if both sides are cash/bank
        # (handled at query level by INNER JOIN on counter account NOT IN cash_accounts)

        # Apply sign: inflow = positive, outflow = negative
        amount = flt(m["amount"])
        signed = amount if cat["is_inflow"] else -amount

        result[cat["activity_type"]][cat["parent_name"]][period_key] += signed

    return result, unmapped


# ---------------------------------------------------------------------------
# REPORT ROW BUILDERS
# ---------------------------------------------------------------------------

ACTIVITY_ORDER = [
    "Операционная деятельность",
    "Инвестиционная деятельность",
    "Финансовая деятельность",
]

ACTIVITY_LABELS = {
    "Операционная деятельность": "Операционная деятельность",
    "Инвестиционная деятельность": "Инвестиционная деятельность",
    "Финансовая деятельность": "Финансовая деятельность",
}


def build_report_rows(aggregated, account_map, periods, period_openings):
    rows = []

    # --- Opening balance row (per period) ---
    opening_row = {
        "label": "Денег на начало месяца",
        "is_balance_row": True,
        "row_type": "balance",
    }
    for p in periods:
        opening_row[p["key"]] = flt(period_openings.get(p["key"], 0))
    rows.append(opening_row)

    # net[period_key] = total net flow across all activities for that period
    net = defaultdict(float)

    for activity in ACTIVITY_ORDER:
        cats_in_activity = sorted(
            [
                v for v in _unique_categories(account_map).values()
                if v["activity_type"] == activity
            ],
            key=lambda x: x["sort_order"],
        )

        rows.append(_header_row(ACTIVITY_LABELS[activity]))

        activity_period_totals = defaultdict(float)

        for cat in cats_in_activity:
            parent_name = cat["parent_name"]
            period_data = aggregated.get(activity, {}).get(parent_name, {})

            row = {"label": cat["category_name"], "row_type": "data"}
            for p in periods:
                val = flt(period_data.get(p["key"], 0))
                row[p["key"]] = val
                activity_period_totals[p["key"]] += val
                net[p["key"]] += val

            rows.append(row)

        sub = _subtotal_row(activity, activity_period_totals, periods)
        rows.append(sub)
        rows.append(_spacer_row())

    # --- Closing balance row: opening + net for that period ---
    closing_row = {
        "label": "Денег на конец месяца",
        "is_balance_row": True,
        "row_type": "balance",
    }
    for p in periods:
        opening = flt(period_openings.get(p["key"], 0))
        closing_row[p["key"]] = opening + net[p["key"]]
    rows.append(closing_row)

    return rows


# ---------------------------------------------------------------------------
# ROW HELPERS
# ---------------------------------------------------------------------------

def _unique_categories(account_map):
    """Deduplicate by parent_name — returns {parent_name: cat_info}."""
    seen = {}
    for acc_info in account_map.values():
        pn = acc_info["parent_name"]
        if pn not in seen:
            seen[pn] = {
                "parent_name": pn,
                "category_name": acc_info["category_name"],
                "activity_type": acc_info["activity_type"],
                "sort_order": acc_info["sort_order"],
                "is_inflow": acc_info["is_inflow"],
            }
    return seen


def _header_row(label):
    return {
        "label": label,
        "is_activity_header": True,
        "row_type": "header",
    }


def _subtotal_row(activity, period_totals, periods):
    row = {
        "label": f"Итого: {activity}",
        "is_subtotal": True,
        "row_type": "subtotal",
    }
    for p in periods:
        row[p["key"]] = flt(period_totals.get(p["key"], 0))
    return row


def _spacer_row():
    return {"label": "", "row_type": "spacer"}


# ---------------------------------------------------------------------------
# CACHE INVALIDATION  (called from hooks.py on_update / on_trash)
# ---------------------------------------------------------------------------

def clear_cache(doc=None, method=None):
    frappe.cache().delete_value("direct_cash_flow_account_map_v2")
