"""
Direct Cash Flow Report (ДДС — Движение Денежных Средств)
App     : armada
Module  : armada_custom_app

Data sources  : Payment Entry (primary) + Journal Entry (secondary)
Mapping       : Cash Flow Categories + Cash Flow Categories Item
Performance   : 4 SQL queries max, account_map cached 5 min, no N+1

Reorder API   : save_category_order()   — drag-and-drop persistence
               get_categories_for_reorder() — dialog data loader
Concurrency   : Single writer model (kassa admin / System Manager only)
               Readers get fresh order on next cache expiry (≤5 min)

Tree mode     : Categories are parent rows, Accounts are child rows.
               Default: all categories collapsed.
               PDF export: account rows are excluded (categories only).
"""

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from collections import defaultdict
from datetime import date, timedelta
import calendar


# ---------------------------------------------------------------------------
# ROLES ALLOWED TO REORDER
# ---------------------------------------------------------------------------

REORDER_ALLOWED_ROLES = {"System Manager", "kassa admin", "Accounts Manager"}


def _can_reorder():
    """Return True if the current user has write permission on category order."""
    user_roles = set(frappe.get_roles(frappe.session.user))
    return bool(user_roles & REORDER_ALLOWED_ROLES)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    validate_filters(filters)

    periods       = get_periods(filters)
    columns       = get_columns(periods)
    account_map   = build_account_map()
    cash_accounts = get_cash_bank_accounts(filters.company)

    period_openings = get_period_opening_balances(
        filters.company, filters.from_date, periods, cash_accounts
    )

    movements = get_all_movements(filters, cash_accounts)
    aggregated, account_aggregated, unmapped = aggregate_movements(
        movements, account_map, periods
    )
    data = build_report_rows(
        aggregated, account_aggregated, account_map, periods, period_openings
    )

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
    1: "Январь", 2: "Февраль", 3: "Март",     4: "Апрель",
    5: "Май",    6: "Июнь",    7: "Июль",     8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def get_periods(filters):
    from_date    = getdate(filters.from_date)
    to_date      = getdate(filters.to_date)
    display_type = filters.get("display_type", "Monthly")
    periods      = []

    if display_type == "Monthly":
        y, m = from_date.year, from_date.month
        while date(y, m, 1) <= to_date:
            last_day = calendar.monthrange(y, m)[1]
            p_start  = date(y, m, 1)
            p_end    = min(date(y, m, last_day), to_date)
            periods.append({
                "key":   f"{y}_{m:02d}",
                "label": f"{MONTH_NAMES_RU[m]} {y}",
                "start": p_start,
                "end":   p_end,
            })
            m += 1
            if m > 12:
                m = 1; y += 1

    elif display_type == "Quarterly":
        y, m = from_date.year, from_date.month
        q_start_month = ((m - 1) // 3) * 3 + 1
        current = date(y, q_start_month, 1)
        while current <= to_date:
            q         = (current.month - 1) // 3 + 1
            q_end_mo  = q * 3
            q_end_day = calendar.monthrange(current.year, q_end_mo)[1]
            p_end     = min(date(current.year, q_end_mo, q_end_day), to_date)
            p_start   = max(current, from_date)
            periods.append({
                "key":   f"{current.year}_Q{q}",
                "label": f"Q{q} {current.year}",
                "start": p_start,
                "end":   p_end,
            })
            next_mo = q_end_mo + 1
            if next_mo > 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, next_mo, 1)

    elif display_type == "Weekly":
        current  = from_date - timedelta(days=from_date.weekday())
        week_num = 0
        while current <= to_date:
            p_start  = max(current, from_date)
            p_end    = min(current + timedelta(days=6), to_date)
            week_num += 1
            periods.append({
                "key":   f"W{week_num}_{current.strftime('%Y%m%d')}",
                "label": f"{p_start.strftime('%d.%m')} - {p_end.strftime('%d.%m.%Y')}",
                "start": p_start,
                "end":   p_end,
            })
            current += timedelta(days=7)

    elif display_type == "Daily":
        current = from_date
        while current <= to_date:
            periods.append({
                "key":   current.strftime("%Y%m%d"),
                "label": current.strftime("%d.%m.%Y"),
                "start": current,
                "end":   current,
            })
            current += timedelta(days=1)

    return periods


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def get_columns(periods):
    cols = [{
        "fieldname": "label",
        "label":     _("Category"),
        "fieldtype": "Data",
        "width":     320,
    }]
    for p in periods:
        cols.append({
            "fieldname": p["key"],
            "label":     p["label"],
            "fieldtype": "Currency",
            "width":     130,
        })
    return cols


# ---------------------------------------------------------------------------
# ACCOUNT MAP  (cached 5 min)
# ---------------------------------------------------------------------------

def build_account_map():
    cache_key = "direct_cash_flow_account_map_v2"
    cached    = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    parents    = frappe.get_all(
        "Cash Flow Categories",
        fields=["name", "category_name", "activity_type", "is_inflow", "sort_order"],
    )
    parent_map = {p["name"]: p for p in parents}

    children = frappe.get_all(
        "Cash Flow Categories Item",
        fields=["parent", "direct_expence_account", "account_label", "direction_override"],
        filters={"parenttype": "Cash Flow Categories"},
    )

    account_map = {}
    for child in children:
        acc    = child.get("direct_expence_account")
        if not acc:
            continue
        parent = parent_map.get(child["parent"])
        if not parent:
            continue

        override = child.get("direction_override") or ""
        if override == "Приход (Inflow)":
            effective_inflow = 1
        elif override == "Расход (Outflow)":
            effective_inflow = 0
        else:
            effective_inflow = cint(parent["is_inflow"])

        display_label = child.get("account_label") or parent["category_name"]

        account_map[acc] = {
            "category_name":      parent["category_name"],
            "display_label":      display_label,
            "activity_type":      parent["activity_type"],
            "is_inflow":          effective_inflow,
            "sort_order":         flt(parent["sort_order"]),
            "parent_name":        parent["name"],
            "direction_override": override,
        }

    frappe.cache().set_value(cache_key, account_map, expires_in_sec=300)
    return account_map


# ---------------------------------------------------------------------------
# CASH / BANK ACCOUNTS
# ---------------------------------------------------------------------------

def get_cash_bank_accounts(company):
    return frappe.get_all(
        "Account",
        filters={
            "company":      company,
            "account_type": ["in", ["Cash", "Bank"]],
            "is_group":     0,
        },
        pluck="name",
    )


# ---------------------------------------------------------------------------
# OPENING BALANCE — PER PERIOD
# ---------------------------------------------------------------------------

def get_period_opening_balances(company, from_date, periods, cash_accounts):
    if not cash_accounts or not periods:
        return {p["key"]: 0.0 for p in periods}

    last_period_end = periods[-1]["end"]

    monthly_net = frappe.db.sql(
        """
        SELECT
            YEAR(posting_date)  AS yr,
            MONTH(posting_date) AS mo,
            SUM(debit - credit) AS net
        FROM `tabGL Entry`
        WHERE
            account          IN %(accounts)s
            AND company       = %(company)s
            AND posting_date <= %(last_date)s
            AND is_cancelled  = 0
        GROUP BY YEAR(posting_date), MONTH(posting_date)
        ORDER BY yr, mo
        """,
        {"accounts": cash_accounts, "company": company, "last_date": last_period_end},
        as_dict=True,
    )

    def balance_before_date(d):
        total = 0.0
        for row in monthly_net:
            yr, mo   = int(row["yr"]), int(row["mo"])
            last_day = calendar.monthrange(yr, mo)[1]
            if date(yr, mo, last_day) < d:
                total += flt(row["net"])
        return total

    return {p["key"]: balance_before_date(p["start"]) for p in periods}


# ---------------------------------------------------------------------------
# MOVEMENTS — SINGLE UNION ALL QUERY
# ---------------------------------------------------------------------------

def get_all_movements(filters, cash_accounts):
    if not cash_accounts:
        return []

    params = {
        "company":       filters.company,
        "from_date":     filters.from_date,
        "to_date":       filters.to_date,
        "cash_accounts": cash_accounts,
    }

    party_condition = ""
    if filters.get("party_type"):
        party_condition = "AND pe.party_type = %(party_type)s"
        params["party_type"] = filters.party_type

    query = """
        SELECT
            'PE'                    AS source,
            pe.name                 AS voucher_no,
            pe.posting_date,
            pe.payment_type,
            pe.paid_from            AS account_from,
            pe.paid_to              AS account_to,
            pe.base_paid_amount     AS amount,
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
            'JE'                    AS source,
            je.name                 AS voucher_no,
            je.posting_date,
            CASE
                WHEN jea_counter.debit > 0 THEN 'Receive'
                ELSE 'Pay'
            END                     AS payment_type,
            jea_counter.account     AS account_from,
            NULL                    AS account_to,
            CASE
                WHEN jea_counter.debit > 0
                    THEN jea_counter.debit_in_account_currency
                ELSE jea_counter.credit_in_account_currency
            END                     AS amount,
            NULL AS party_type,
            NULL AS party
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea_counter
            ON jea_counter.parent  = je.name
            AND jea_counter.account NOT IN %(cash_accounts)s
        WHERE
            je.docstatus   = 1
            AND je.company = %(company)s
            AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND je.name IN (
                SELECT DISTINCT parent
                FROM `tabJournal Entry Account`
                WHERE account IN %(cash_accounts)s
            )
    """.format(party_condition=party_condition)

    return frappe.db.sql(query, params, as_dict=True)


# ---------------------------------------------------------------------------
# PERIOD KEY LOOKUP
# ---------------------------------------------------------------------------

def get_period_key(posting_date, periods):
    d = getdate(posting_date)
    for p in periods:
        if p["start"] <= d <= p["end"]:
            return p["key"]
    return None


# ---------------------------------------------------------------------------
# AGGREGATION
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AGGREGATION
# ---------------------------------------------------------------------------

def aggregate_movements(movements, account_map, periods):
    """
    Returns:
      result         : aggregated[activity][parent_name][period_key]  — category totals
      account_result : account_aggregated[parent_name][account][period_key] — per-account
      unmapped       : list of unmapped movements

    Sign logic:
      PE  → direction from payment_type (Receive = +, Pay = −)
            is_inflow faqat qaysi kategoriyaga tushishini belgilaydi, sign uchun emas
      JE  → direction from is_inflow (counter debit = outflow → −, counter credit = inflow → +)
    """
    result         = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    account_result = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    unmapped       = []

    for m in movements:
        if m["source"] == "PE":
            mapping_account = (
                m["account_from"] if m["payment_type"] == "Receive"
                else m["account_to"]
            )
        else:
            mapping_account = m["account_from"]

        cat = account_map.get(mapping_account)
        if not cat:
            unmapped.append({
                "voucher_no":      m.get("voucher_no"),
                "mapping_account": mapping_account,
                "amount":          m.get("amount"),
            })
            continue

        period_key = get_period_key(m["posting_date"], periods)
        if not period_key:
            continue

        amount = flt(m["amount"])

        if m["source"] == "PE":
            # PE uchun: payment_type aniq yo'nalishni beradi.
            # Receive → pul KIRDI  → musbat
            # Pay     → pul CHIQDI → manfiy
            # Bu holat PE Pay → inflow-mapped account (masalan, 1310-Debtors)
            # ni ham to'g'ri ishlaydi: signed = −amount (cash went out).
            signed = amount if m["payment_type"] == "Receive" else -amount
        else:
            # JE uchun: is_inflow kategoriya konfiguratsiyasidan keladi.
            # counter_debit (xarajat account debited, cash credited) → outflow → manfiy
            # counter_credit (daromad/debitor credited, cash debited) → inflow → musbat
            signed = amount if cat["is_inflow"] else -amount

        result[cat["activity_type"]][cat["parent_name"]][period_key] += signed
        account_result[cat["parent_name"]][mapping_account][period_key] += signed

    return result, account_result, unmapped

# ---------------------------------------------------------------------------
# REPORT ROW BUILDERS
# ---------------------------------------------------------------------------

ACTIVITY_ORDER = [
    "Операционная деятельность",
    "Инвестиционная деятельность",
    "Финансовая деятельность",
]

ACTIVITY_LABELS = {
    "Операционная деятельность":   "Операционная деятельность",
    "Инвестиционная деятельность": "Инвестиционная деятельность",
    "Финансовая деятельность":     "Финансовая деятельность",
}


def build_report_rows(aggregated, account_aggregated, account_map, periods, period_openings):
    rows = []

    opening_row = {
        "label": "Денег на начало месяца",
        "indent": 0,
        "is_balance_row": True,
        "row_type": "balance",
    }
    for p in periods:
        opening_row[p["key"]] = flt(period_openings.get(p["key"], 0))
    rows.append(opening_row)

    net = defaultdict(float)

    # Build per-category account list (sorted by account name for stable display)
    accounts_by_category = _accounts_by_category(account_map)

    for activity in ACTIVITY_ORDER:
        cats_in_activity = sorted(
            [v for v in _unique_categories(account_map).values()
             if v["activity_type"] == activity],
            key=lambda x: x["sort_order"],
        )

        rows.append(_header_row(ACTIVITY_LABELS[activity]))

        activity_period_totals = defaultdict(float)

        for cat in cats_in_activity:
            parent_name   = cat["parent_name"]
            category_name = cat["category_name"]
            period_data   = aggregated.get(activity, {}).get(parent_name, {})

            # ── Parent (category) row ─────────────────────────────────────
            category_row = {
                "label":     category_name,
                "indent":    0,
                "row_type":  "data",
                "is_inflow": cint(cat["is_inflow"]),
                "_id":       category_name,
                "parent":    None,
                "has_value": True,
            }
            for p in periods:
                val = flt(period_data.get(p["key"], 0))
                category_row[p["key"]] = val
                activity_period_totals[p["key"]] += val
                net[p["key"]] += val
            rows.append(category_row)

            # ── Child (account) rows ──────────────────────────────────────
            # NOTE: account amounts are already signed during aggregation,
            # so the sum of children equals the category total — no double counting.
            for acc in accounts_by_category.get(parent_name, []):
                acc_period_data = account_aggregated.get(parent_name, {}).get(acc, {})

                # Skip accounts that have zero movement in every period
                # (purely cosmetic — declutters the tree).
                if not any(flt(acc_period_data.get(p["key"], 0)) for p in periods):
                    continue

                acc_info = account_map.get(acc, {})
                acc_row = {
                    "label":     acc,
                    "indent":    1,
                    "row_type":  "account",
                    "is_inflow": cint(acc_info.get("is_inflow", -1)),
                    "_id":       f"{category_name}::{acc}",
                    "parent":    category_name,
                    "has_value": True,
                }
                for p in periods:
                    acc_row[p["key"]] = flt(acc_period_data.get(p["key"], 0))
                rows.append(acc_row)

        rows.append(_subtotal_row(activity, activity_period_totals, periods))
        rows.append(_spacer_row())

    closing_row = {
        "label": "Денег на конец месяца",
        "indent": 0,
        "is_balance_row": True,
        "row_type": "balance",
    }
    for p in periods:
        closing_row[p["key"]] = flt(period_openings.get(p["key"], 0)) + net[p["key"]]
    rows.append(closing_row)

    return rows


# ---------------------------------------------------------------------------
# ROW HELPERS
# ---------------------------------------------------------------------------

def _unique_categories(account_map):
    seen = {}
    for acc_info in account_map.values():
        pn = acc_info["parent_name"]
        if pn not in seen:
            seen[pn] = {
                "parent_name":   pn,
                "category_name": acc_info["category_name"],
                "activity_type": acc_info["activity_type"],
                "sort_order":    acc_info["sort_order"],
                "is_inflow":     acc_info["is_inflow"],
            }
    return seen


def _accounts_by_category(account_map):
    """Group accounts by their parent category name, sorted alphabetically."""
    grouped = defaultdict(list)
    for acc, info in account_map.items():
        grouped[info["parent_name"]].append(acc)
    for parent in grouped:
        grouped[parent].sort()
    return grouped


def _header_row(label):
    return {
        "label": label,
        "indent": 0,
        "is_activity_header": True,
        "row_type": "header",
    }


def _subtotal_row(activity, period_totals, periods):
    row = {
        "label":       f"Итого: {activity}",
        "indent":      0,
        "is_subtotal": True,
        "row_type":    "subtotal",
    }
    for p in periods:
        row[p["key"]] = flt(period_totals.get(p["key"], 0))
    return row


def _spacer_row():
    return {"label": "", "indent": 0, "row_type": "spacer"}


# ---------------------------------------------------------------------------
# CACHE INVALIDATION  (called from hooks.py on_update / on_trash)
# ---------------------------------------------------------------------------

def clear_cache(doc=None, method=None):
    frappe.cache().delete_value("direct_cash_flow_account_map_v2")


# ---------------------------------------------------------------------------
# DRAG-AND-DROP REORDER API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_categories_for_reorder():
    """
    Returns all Cash Flow Categories grouped-ready for the reorder dialog.
    Only users with reorder permission receive the can_reorder flag = True.
    Readers get the same data but UI renders in read-only mode.
    """
    categories = frappe.get_all(
        "Cash Flow Categories",
        fields=["name", "category_name", "activity_type", "sort_order"],
        order_by="sort_order asc, creation asc",
    )

    return {
        "categories":  categories,
        "can_reorder": _can_reorder(),
    }


@frappe.whitelist()
def save_category_order(ordered_names):
    """
    Persists the new drag-and-drop order for Cash Flow Categories.

    Protocol:
    - Only REORDER_ALLOWED_ROLES can call this.
    - ordered_names: JSON list of category `name` values in desired order.
    - Uses gap-1000 float spacing: 1000.0, 2000.0, 3000.0 …
      → Supports up to 999 inserts between any two items before
        a normalize pass is needed.
    - Does NOT touch activity_type — cross-group drag is intentionally
      disabled in the UI. This is a server-side safety guard as well.
    - Invalidates account_map cache on success.
    - Returns an order_hash (sorted names joined) so client can verify
      round-trip integrity.
    """
    import json
    import hashlib

    # ── Permission guard ──────────────────────────────────────────────────
    if not _can_reorder():
        frappe.throw(
            _("Недостаточно прав для изменения порядка категорий."),
            frappe.PermissionError,
        )

    # ── Input parsing ─────────────────────────────────────────────────────
    if isinstance(ordered_names, str):
        try:
            ordered_names = json.loads(ordered_names)
        except (ValueError, TypeError):
            frappe.throw(_("Invalid input: could not parse ordered_names JSON"))

    if not ordered_names or not isinstance(ordered_names, list):
        frappe.throw(_("Invalid input: expected non-empty list of category names"))

    # ── Validate all names exist and belong to Cash Flow Categories ───────
    existing = {
        r["name"]
        for r in frappe.get_all("Cash Flow Categories", fields=["name"])
    }
    invalid = [n for n in ordered_names if n not in existing]
    if invalid:
        frappe.throw(
            _("Unknown category name(s): {0}").format(", ".join(invalid))
        )

    # ── Write gap-1000 float sort_order ───────────────────────────────────
    # update_modified=False: do not pollute modified/modified_by audit trail
    # for a cosmetic reorder operation.
    for i, name in enumerate(ordered_names):
        frappe.db.set_value(
            "Cash Flow Categories",
            name,
            "sort_order",
            float((i + 1) * 1000),
            update_modified=False,
        )

    frappe.db.commit()

    # ── Invalidate cache so next report load picks up new order ──────────
    clear_cache()

    # ── Return integrity hash for client-side verification ───────────────
    order_hash = hashlib.md5(
        ",".join(ordered_names).encode()
    ).hexdigest()[:8]

    return {
        "status":     "ok",
        "count":      len(ordered_names),
        "order_hash": order_hash,
    }


@frappe.whitelist()
def normalize_sort_order():
    """
    One-time maintenance utility.
    Re-spaces all sort_order values to multiples of 1000
    without changing relative order.

    Call via:
        bench --site <site> execute \
        armada.armada_custom_app.report.direct_cash_flow.direct_cash_flow.normalize_sort_order
    OR via frappe.call() from browser console (System Manager only).
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager can run normalize_sort_order."),
                     frappe.PermissionError)

    cats = frappe.get_all(
        "Cash Flow Categories",
        fields=["name", "activity_type"],
        order_by="sort_order asc, creation asc",
    )

    # Normalize per activity group to keep intra-group gaps clean
    from collections import defaultdict as _dd
    groups = _dd(list)
    for c in cats:
        groups[c["activity_type"]].append(c["name"])

    ACTIVITY_ORDER_LOCAL = [
        "Операционная деятельность",
        "Инвестиционная деятельность",
        "Финансовая деятельность",
    ]

    global_index = 0
    for act in ACTIVITY_ORDER_LOCAL:
        for name in groups.get(act, []):
            global_index += 1
            frappe.db.set_value(
                "Cash Flow Categories",
                name,
                "sort_order",
                float(global_index * 1000),
                update_modified=False,
            )

    frappe.db.commit()
    clear_cache()

    return {"status": "ok", "normalized": global_index}


# ===========================================================================
# PDF EXPORT  —  pixel-perfect match to the reference Armada Cash Flow PDF
# ===========================================================================

# ── P&L expense groups (mirrors CoA hierarchy under 5200 - Indirect Expenses).
# Categories whose accounts sit under these parent accounts are collapsed
# into a single group row in the PDF. Accounts outside these parents
# (Клиент/Поставщик receivable-payable accounts, 5232 Налог на прибыль)
# keep their own category row — same as the P&L layout.
PNL_GROUP_ORDER = ["52001", "52002", "52003"]

PNL_GROUP_LABELS = {
    "52001": "Общепроизводственные расходы",
    "52002": "Административные расходы",
    "52003": "Коммерческие расходы",
}

# Categories hidden from the PDF entirely. Their cash movement still counts
# in activity subtotals and closing balance — only the row is not shown.
PDF_HIDDEN_CATEGORIES = {"Налог на прибыль"}


def _category_pnl_groups(account_map):
    """category_name → P&L group code ('52001'/'52002'/'52003'),
    resolved via each mapped account's parent in the Chart of Accounts."""
    accounts = list(account_map.keys())
    if not accounts:
        return {}

    parent_by_account = dict(
        frappe.get_all(
            "Account",
            filters={"name": ["in", accounts]},
            fields=["name", "parent_account"],
            as_list=True,
        )
    )

    groups = {}
    for acc, info in account_map.items():
        code = str(parent_by_account.get(acc) or "").split(" - ")[0].strip()
        if code in PNL_GROUP_LABELS:
            groups.setdefault(info["category_name"], code)
    return groups


def _group_pdf_rows(rows, period_keys, cat_groups):
    """Collapse groupable category rows into P&L group rows (PDF only).

    Group rows are inserted at the position of the first collapsed row,
    so ungrouped rows before them (Клиент, Поставщик) keep their place and
    ungrouped rows after them (Налог на прибыль) land below the groups.
    """
    out       = []
    bucket    = {}     # group code → aggregated row
    insert_at = None

    def flush():
        nonlocal bucket, insert_at
        if bucket:
            group_rows = [bucket[c] for c in PNL_GROUP_ORDER if c in bucket]
            out[insert_at:insert_at] = group_rows
        bucket, insert_at = {}, None

    for row in rows:
        rt = row.get("row_type", "")

        if rt == "data" and row.get("label") in cat_groups:
            code = cat_groups[row["label"]]
            grow = bucket.get(code)
            if grow is None:
                grow = {
                    "label":     PNL_GROUP_LABELS[code],
                    "indent":    0,
                    "row_type":  "data",
                    "is_inflow": 0,
                    "has_value": True,
                }
                for k in period_keys:
                    grow[k] = 0.0
                bucket[code] = grow
                if insert_at is None:
                    insert_at = len(out)
            for k in period_keys:
                grow[k] += flt(row.get(k, 0))
            continue

        if rt in ("header", "subtotal", "balance"):
            flush()
        out.append(row)

    flush()
    return out


@frappe.whitelist()
def export_pdf(filters=None):
    """
    Whitelisted endpoint called from the JS 'Экспорт PDF' button.
    Returns base64-encoded landscape-A4 PDF for client-side blob download.

    NOTE: account-level rows (row_type='account') are explicitly excluded
          from the PDF output — PDF stays category-level only.
          Expense categories are further collapsed into P&L group rows
          (Общепроизводственные / Административные / Коммерческие).
    """
    import json
    import base64

    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = frappe._dict(filters or {})
    validate_filters(filters)

    columns, data = execute(filters)

    # ── Strip account-level rows for PDF (categories-only view) ──────────
    data = [r for r in data if r.get("row_type") != "account"]

    # ── Collapse expense categories into P&L group rows ──────────────────
    period_keys = [c["fieldname"] for c in columns if c["fieldname"] != "label"]
    cat_groups  = _category_pnl_groups(build_account_map())
    data        = _group_pdf_rows(data, period_keys, cat_groups)

    # ── Hide excluded category rows (values stay in the totals) ──────────
    data = [
        r for r in data
        if not (r.get("row_type") == "data"
                and str(r.get("label", "")).strip() in PDF_HIDDEN_CATEGORIES)
    ]

    html = _build_pdf_html(columns, data, filters)

    from frappe.utils.pdf import get_pdf

    pdf_options = {
        "orientation":             "Landscape",
        "page-size":               "A4",
        "margin-top":              "8mm",
        "margin-bottom":           "8mm",
        "margin-left":             "6mm",
        "margin-right":            "6mm",
        "encoding":                "UTF-8",
        "no-outline":              None,
        "disable-smart-shrinking": None,
    }

    pdf_bytes = get_pdf(html, pdf_options)
    return base64.b64encode(pdf_bytes).decode("utf-8")


# ---------------------------------------------------------------------------
# ROW REORDER  —  Frappe order → PDF order
# ---------------------------------------------------------------------------

def _reorder_for_pdf(rows, period_cols):
    pdf_rows = []
    i = 0
    n = len(rows)

    while i < n:
        row = rows[i]
        rt  = row.get("row_type", "")

        if rt == "balance":
            pdf_rows.append(dict(row, _pdf_type="balance"))
            i += 1

        elif rt == "header":
            data_buf     = []
            subtotal_row = None
            j            = i + 1

            while j < n:
                r   = rows[j]
                rrt = r.get("row_type", "")
                if rrt == "data":
                    data_buf.append(r)
                elif rrt == "subtotal":
                    subtotal_row = r
                    j += 1
                    break
                elif rrt in ("header", "balance"):
                    break
                j += 1

            if subtotal_row:
                act_label = subtotal_row.get("label", "")
                if act_label.startswith("Итого: "):
                    act_label = act_label[7:]
                act_row = dict(subtotal_row, label=act_label, _pdf_type="activity")
            else:
                act_row = dict(row, _pdf_type="activity")

            pdf_rows.append(act_row)
            for dr in data_buf:
                pdf_rows.append(dict(dr, _pdf_type="data"))

            pdf_rows.append({"_pdf_type": "spacer", "label": ""})
            i = j

        elif rt in ("subtotal", "spacer"):
            i += 1

        else:
            i += 1

    while pdf_rows and pdf_rows[-1].get("_pdf_type") == "spacer":
        pdf_rows.pop()

    pdf_rows.append({"_pdf_type": "spacer", "label": ""})
    raznica = {"_pdf_type": "raznica", "label": "Разница с балансом"}
    for col in period_cols:
        raznica[col["fieldname"]] = 0
    pdf_rows.append(raznica)

    return pdf_rows


# ---------------------------------------------------------------------------
# HTML BUILDER
# ---------------------------------------------------------------------------

def _build_pdf_html(columns, data, filters):
    period_cols  = [c for c in columns if c["fieldname"] != "label"]
    n            = len(period_cols)
    display_type = filters.get("display_type", "Monthly")
    company      = filters.get("company", "")
    generated    = date.today().strftime("%d.%m.%Y")

    label_pct = 28
    num_pct   = round((100 - label_pct) / max(n, 1), 4)
    label_w   = f"{label_pct}%"
    num_w     = f"{num_pct}%"

    split_hdrs = []
    for col in period_cols:
        lbl   = col["label"]
        parts = lbl.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            split_hdrs.append((parts[1], parts[0]))
        else:
            split_hdrs.append(("", lbl))

    use_two_rows = display_type in ("Monthly", "Quarterly")
    pdf_rows     = _reorder_for_pdf(data, period_cols)

    css = """
@page { size: A4 landscape; margin: 8mm 6mm; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 8pt;
    color: #1C2833;
    background: #FFFFFF;
}
table {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
}
td { overflow: hidden; word-wrap: break-word; }
.tr-title td {
    background-color: #1C2833;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 11pt;
    padding: 7px 10px;
    border: none;
    letter-spacing: 0.2px;
}
.tr-year td {
    background-color: #D5D8DC;
    color: #1C2833;
    font-weight: 700;
    font-size: 8pt;
    text-align: center;
    padding: 4px 4px;
    border: 1px solid #FFFFFF;
}
.tr-year td.lbl { text-align: left; padding-left: 8px; }
.tr-month td {
    background-color: #D5D8DC;
    color: #1C2833;
    font-weight: 700;
    font-size: 8pt;
    text-align: center;
    padding: 4px 4px;
    border: 1px solid #FFFFFF;
}
.tr-month td.lbl { text-align: left; padding-left: 8px; }
.tr-colhdr td {
    background-color: #D5D8DC;
    color: #1C2833;
    font-weight: 700;
    font-size: 7.5pt;
    text-align: center;
    padding: 4px 3px;
    border: 1px solid #FFFFFF;
}
.tr-colhdr td.lbl { text-align: left; padding-left: 8px; }
.tr-balance td {
    background-color: #E74C3C;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 8.5pt;
    padding: 4px 6px;
    border: 1px solid #FFFFFF;
}
.tr-activity td {
    background-color: #E67E22;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 8.5pt;
    padding: 4px 6px;
    border: 1px solid #FFFFFF;
}
.tr-data td {
    background-color: #FFFFFF;
    color: #1C2833;
    font-size: 7.8pt;
    font-weight: 700;
    padding: 2.5px 5px;
    border: 1px solid #FFFFFF;
}
.tr-data-alt td {
    background-color: #FAFAFA;
    color: #1C2833;
    font-size: 7.8pt;
    font-weight: 700;
    padding: 2.5px 5px;
    border: 1px solid #FFFFFF;
}
.tr-spacer td {
    background-color: #FFFFFF;
    border: none;
    height: 4px;
    padding: 0;
}
.tr-raznica td {
    background-color: #FFFFFF;
    font-weight: 700;
    font-size: 8pt;
    padding: 4px 6px;
    border: 1px solid #FFFFFF;
    border-top: 2px solid #D5D8DC;
}
.tr-raznica td.lbl { color: #E74C3C; }
.tr-raznica td.num { color: #E74C3C; }
td.lbl { text-align: left; }
td.num { text-align: right; }
.nn  { color: #C0392B; }
.np  { color: #27AE60; }
.nz  { color: #1C2833; }
.nw  { color: #FFFFFF; }
.nwp { color: #FFFFFF; }
.footer {
    margin-top: 5px;
    font-size: 7pt;
    color: #888888;
    text-align: right;
}
"""

    trs = []

    trs.append(
        f'<tr class="tr-title">'
        f'<td class="lbl" colspan="{n + 1}">Движение Денежных Средств</td>'
        f'</tr>'
    )

    if use_two_rows:
        year_cells = "".join(
            f'<td class="num" style="width:{num_w};">{_esc(yr)}</td>'
            for yr, _ in split_hdrs
        )
        trs.append(
            f'<tr class="tr-year">'
            f'<td class="lbl" style="width:{label_w};">Год</td>'
            f'{year_cells}</tr>'
        )
        month_cells = "".join(
            f'<td class="num" style="width:{num_w};">{_esc(mn)}</td>'
            for _, mn in split_hdrs
        )
        trs.append(
            f'<tr class="tr-month">'
            f'<td class="lbl" style="width:{label_w};">Месяц</td>'
            f'{month_cells}</tr>'
        )
    else:
        col_cells = "".join(
            f'<td class="num" style="width:{num_w};">{_esc(c["label"])}</td>'
            for c in period_cols
        )
        trs.append(
            f'<tr class="tr-colhdr">'
            f'<td class="lbl" style="width:{label_w};">Период</td>'
            f'{col_cells}</tr>'
        )

    data_idx = 0

    for row in pdf_rows:
        pt = row.get("_pdf_type", "data")

        if pt == "spacer":
            trs.append(f'<tr class="tr-spacer"><td colspan="{n + 1}"></td></tr>')
            data_idx = 0
            continue

        if pt == "balance":
            tr_cls   = "tr-balance"
            lbl_html = _esc(row.get("label", ""))
            colored  = True
        elif pt == "activity":
            tr_cls   = "tr-activity"
            lbl_html = _esc(row.get("label", ""))
            colored  = True
        elif pt == "raznica":
            tr_cls   = "tr-raznica"
            lbl_html = _esc(row.get("label", ""))
            td_lbl   = f'<td class="lbl">{lbl_html}</td>'
            td_nums  = "".join(
                f'<td class="num"><span style="color:#E74C3C;font-weight:700;">'
                f'{_fmt_raznica(row.get(c["fieldname"]))}</span></td>'
                for c in period_cols
            )
            trs.append(f'<tr class="{tr_cls}">{td_lbl}{td_nums}</tr>')
            continue
        else:
            tr_cls   = "tr-data" if data_idx % 2 == 0 else "tr-data-alt"
            data_idx += 1
            lbl_html = _prefix_html(row.get("label", ""), cint(row.get("is_inflow", -1)))
            colored  = False

        td_lbl  = f'<td class="lbl">{lbl_html}</td>'
        td_nums = "".join(
            f'<td class="num">{_fmt_num(row.get(c["fieldname"]), colored)}</td>'
            for c in period_cols
        )
        trs.append(f'<tr class="{tr_cls}">{td_lbl}{td_nums}</tr>')

    table_html  = f'<table>{"".join(trs)}</table>'
    footer_html = (
        f'<div class="footer">'
        f'Компания: {_esc(company)}&nbsp;&nbsp;|&nbsp;&nbsp;'
        f'Сформировано: {generated}'
        f'</div>'
    )

    return (
        '<!DOCTYPE html>\n<html lang="ru">\n<head>\n'
        f'<meta charset="UTF-8">\n<style>{css}</style>\n</head>\n'
        f'<body>\n{table_html}\n{footer_html}\n</body>\n</html>'
    )


# ---------------------------------------------------------------------------
# MICRO-HELPERS
# ---------------------------------------------------------------------------

def _esc(text):
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _prefix_html(label, is_inflow=-1):
    txt = _esc(str(label or ""))
    if is_inflow == 1:
        return f'<span style="color:#27AE60;font-weight:700;">+ {txt}</span>'
    if is_inflow == 0:
        return f'<span style="color:#C0392B;font-weight:700;">- {txt}</span>'
    return txt


def _fmt_raznica(val):
    v = flt(val)
    if v == 0:
        return "0"
    abs_str = format(abs(round(v)), ",.0f")
    if v < 0:
        return f"({abs_str})"
    return abs_str


def _fmt_num(val, colored=False):
    if val is None or val == "":
        return ""
    v = flt(val)
    abs_str = format(abs(round(v)), ",.0f")
    if colored:
        if v == 0:
            return '<span class="nw">0</span>'
        if v < 0:
            return f'<span class="nw">({abs_str})</span>'
        return f'<span class="nwp">{abs_str}</span>'
    else:
        if v == 0:
            return '<span class="nz">0</span>'
        if v < 0:
            return f'<span class="nn">({abs_str})</span>'
        return f'<span class="np">{abs_str}</span>'
