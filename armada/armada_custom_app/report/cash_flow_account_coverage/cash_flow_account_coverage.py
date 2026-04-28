"""
Cash Flow Account Coverage Report
App    : armada
Module : armada_custom_app

Maqsad : Kompaniyadagi BARCHA aktiv accountlarni ko'rsatish va
         ularning Cash Flow Categories ga biriktirilgan / biriktirilmaganini
         activity type bo'yicha guruhlangan holda vizualizatsiya qilish.

Grouping:
    1. Операционная деятельность  → Mapped → accounts...
                                  → Unmapped → accounts...
    2. Инвестиционная деятельность → ...
    3. Финансовая деятельность     → ...
    4. ✗ Не назначено              → (hech qanday activity ga tegishli emas)

Performance:
    - 2 SQL query (accounts + all mappings)
    - No N+1
    - account_type filter ixtiyoriy

Quick-assign API:
    assign_account_to_category()  — whitelisted, Accounts Manager / kassa admin / System Manager
    remove_account_from_category() — whitelisted, bir xil permission
"""

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import cint
from collections import defaultdict


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

ACTIVITY_ORDER = [
    "Операционная деятельность",
    "Инвестиционная деятельность",
    "Финансовая деятельность",
]

ASSIGN_ALLOWED_ROLES = {"System Manager", "kassa admin", "Accounts Manager"}

# Account types included by default (barcha meaningful types)
ALL_ACCOUNT_TYPES = [
    "Cash", "Bank", "Receivable", "Payable",
    "Tax", "Chargeable", "Expense Account",
    "Income Account", "Temporary",
    "Fixed Asset", "Accumulated Depreciation",
    "Depreciation", "Capital Work in Progress",
    "Expense",  "Income",
    "Cost of Goods Sold", "Stock",
    "Round Off", "Write Off",
    "Liability", "Equity",
]


# ---------------------------------------------------------------------------
# PERMISSION HELPER
# ---------------------------------------------------------------------------

def _can_assign():
    return bool(set(frappe.get_roles(frappe.session.user)) & ASSIGN_ALLOWED_ROLES)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    columns  = _get_columns()
    accounts = _get_accounts(filters)
    mapping  = _get_full_mapping()

    data = _build_rows(accounts, mapping, filters)
    return columns, data


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def _validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is required"))


# ---------------------------------------------------------------------------
# COLUMNS
# ---------------------------------------------------------------------------

def _get_columns():
    return [
        {
            "fieldname": "account_name",
            "label":     _("Account"),
            "fieldtype": "Data",
            "width":     280,
        },
        {
            "fieldname": "account_type",
            "label":     _("Account Type"),
            "fieldtype": "Data",
            "width":     130,
        },
        {
            "fieldname": "is_group",
            "label":     _("Is Group"),
            "fieldtype": "Data",
            "width":     70,
        },
        {
            "fieldname": "category_name",
            "label":     _("Cash Flow Category"),
            "fieldtype": "Data",
            "width":     200,
        },
        {
            "fieldname": "activity_type",
            "label":     _("Activity"),
            "fieldtype": "Data",
            "width":     180,
        },
        {
            "fieldname": "direction",
            "label":     _("Direction"),
            "fieldtype": "Data",
            "width":     110,
        },
        {
            "fieldname": "status",
            "label":     _("Status"),
            "fieldtype": "Data",
            "width":     110,
        },
        # Hidden fields — used by JS for quick-assign dialog
        {
            "fieldname": "account_doc_name",
            "label":     _("Account ID"),
            "fieldtype": "Data",
            "width":     0,
            "hidden":    1,
        },
        {
            "fieldname": "category_item_name",
            "label":     _("Item Name"),
            "fieldtype": "Data",
            "width":     0,
            "hidden":    1,
        },
        {
            "fieldname": "can_assign",
            "label":     _("Can Assign"),
            "fieldtype": "Data",
            "width":     0,
            "hidden":    1,
        },
    ]


# ---------------------------------------------------------------------------
# DATA FETCH — 2 queries total
# ---------------------------------------------------------------------------

def _get_accounts(filters):
    """
    Returns all active (disabled=0) accounts for the company.
    Optionally filtered by account_type.
    Group accounts included (is_group=1) but flagged.
    """
    conditions = {
        "company":  filters.company,
        "disabled": 0,
    }

    # Optional account_type filter
    acct_types = filters.get("account_type")
    if acct_types:
        if isinstance(acct_types, str):
            import json
            try:
                acct_types = json.loads(acct_types)
            except Exception:
                acct_types = [acct_types]
        conditions["account_type"] = ["in", acct_types]

    return frappe.get_all(
        "Account",
        filters=conditions,
        fields=[
            "name",
            "account_name",
            "account_type",
            "is_group",
            "parent_account",
        ],
        order_by="lft asc",   # tree order — parent before children
    )


def _get_full_mapping():
    """
    Returns a dict: account_name → list of mapping info dicts
    One account can theoretically appear in multiple categories.
    We handle that by showing all mappings (rare but valid).

    Single query joining Cash Flow Categories Item + parent.
    """
    rows = frappe.db.sql(
        """
        SELECT
            item.name                  AS item_name,
            item.parent                AS parent_name,
            item.direct_expence_account AS account,
            item.account_label,
            item.direction_override,
            cat.category_name,
            cat.activity_type,
            cat.is_inflow
        FROM `tabCash Flow Categories Item` item
        INNER JOIN `tabCash Flow Categories` cat
            ON cat.name = item.parent
        WHERE
            item.direct_expence_account IS NOT NULL
            AND item.direct_expence_account != ''
        """,
        as_dict=True,
    )

    mapping = defaultdict(list)
    for r in rows:
        mapping[r["account"]].append(r)
    return mapping


# ---------------------------------------------------------------------------
# ROW BUILDER
# ---------------------------------------------------------------------------

def _build_rows(accounts, mapping, filters):
    """
    Grouping structure:
        [activity header]
          [Mapped sub-header]
            account rows...
          [Unmapped sub-header]
            account rows...
        [spacer]
        ...
        [Не назначено header]  ← accounts with no mapping at all
          account rows...
        [spacer]
        [Summary row]
    """
    show_unmapped_only = cint(filters.get("show_unmapped_only", 0))

    can_assign = _can_assign()

    # Index accounts by name for O(1) lookup
    account_index = {a["name"]: a for a in accounts}

    # Build per-activity buckets: activity → {mapped: [], unmapped: []}
    activity_buckets = {
        act: {"mapped": [], "unmapped": []}
        for act in ACTIVITY_ORDER
    }
    unassigned_bucket = []   # no activity at all

    # Determine primary activity for each account
    # If account is mapped to multiple activities, it appears in each
    # If mapped to same activity multiple times, show first mapping only
    for acc in accounts:
        acc_name  = acc["name"]
        mappings  = mapping.get(acc_name, [])

        if not mappings:
            unassigned_bucket.append({
                "account":  acc,
                "map_info": None,
            })
        else:
            # Group by activity_type
            seen_activities = set()
            for m in mappings:
                act = m.get("activity_type") or "Не назначено"
                if act not in seen_activities:
                    seen_activities.add(act)
                    if act in activity_buckets:
                        activity_buckets[act]["mapped"].append({
                            "account":  acc,
                            "map_info": m,
                        })

    # Also find unmapped within each activity scope — accounts whose
    # account_type typically belongs to that category but has no mapping.
    # We simply put ALL non-mapped non-group accounts into unassigned.
    # Mapped accounts are already placed above.
    mapped_account_names = set(mapping.keys())

    # Rebuild unassigned: strictly accounts with no mapping entry
    unassigned_bucket = []
    for acc in accounts:
        if acc["name"] not in mapped_account_names:
            unassigned_bucket.append({
                "account":  acc,
                "map_info": None,
            })

    rows = []
    total_mapped   = 0
    total_unmapped = 0
    total_group    = 0

    # ── Per-activity sections ─────────────────────────────────────────────
    for act in ACTIVITY_ORDER:
        bucket       = activity_buckets[act]
        mapped_items = bucket["mapped"]

        if not mapped_items and show_unmapped_only:
            continue
        if not mapped_items:
            # Still show header for clarity even if empty
            rows.append(_section_header(act, "activity"))
            rows.append(_empty_row(_("Нет привязанных счетов")))
            rows.append(_spacer())
            continue

        rows.append(_section_header(act, "activity"))

        # Mapped sub-section
        if not show_unmapped_only:
            rows.append(_sub_header(_("✓ Назначено"), "mapped"))
            for item in mapped_items:
                acc      = item["account"]
                map_info = item["map_info"]
                is_grp   = cint(acc.get("is_group", 0))
                if is_grp:
                    total_group += 1
                else:
                    total_mapped += 1

                rows.append(_data_row(
                    account        = acc,
                    map_info       = map_info,
                    status         = "mapped",
                    can_assign     = can_assign,
                ))

        rows.append(_spacer())

    # ── Unassigned section ────────────────────────────────────────────────
    if unassigned_bucket:
        rows.append(_section_header(_("✗ Не назначено"), "unassigned"))

        for item in unassigned_bucket:
            acc    = item["account"]
            is_grp = cint(acc.get("is_group", 0))
            if is_grp:
                total_group += 1
            else:
                total_unmapped += 1

            rows.append(_data_row(
                account    = acc,
                map_info   = None,
                status     = "unmapped",
                can_assign = can_assign,
            ))

        rows.append(_spacer())

    # ── Summary row ───────────────────────────────────────────────────────
    rows.append(_summary_row(total_mapped, total_unmapped, total_group))

    return rows


# ---------------------------------------------------------------------------
# ROW FACTORIES
# ---------------------------------------------------------------------------

def _section_header(label, section_type):
    return {
        "account_name":    label,
        "account_type":    "",
        "is_group":        "",
        "category_name":   "",
        "activity_type":   "",
        "direction":       "",
        "status":          "",
        "account_doc_name": "",
        "category_item_name": "",
        "can_assign":      "0",
        "row_type":        "section_header",
        "section_type":    section_type,
    }


def _sub_header(label, sub_type):
    return {
        "account_name":    label,
        "account_type":    "",
        "is_group":        "",
        "category_name":   "",
        "activity_type":   "",
        "direction":       "",
        "status":          "",
        "account_doc_name": "",
        "category_item_name": "",
        "can_assign":      "0",
        "row_type":        "sub_header",
        "sub_type":        sub_type,
    }


def _data_row(account, map_info, status, can_assign):
    is_grp = cint(account.get("is_group", 0))

    if map_info:
        override  = map_info.get("direction_override") or ""
        if override == "Приход (Inflow)":
            direction = "Приход"
        elif override == "Расход (Outflow)":
            direction = "Расход"
        else:
            direction = "Приход" if cint(map_info.get("is_inflow", 0)) else "Расход"

        category_name = map_info.get("account_label") or map_info.get("category_name") or ""
        activity      = map_info.get("activity_type") or ""
        item_name     = map_info.get("item_name") or ""
    else:
        direction     = ""
        category_name = ""
        activity      = ""
        item_name     = ""

    # Group accounts cannot be assigned — they are structural
    effective_can_assign = can_assign and not is_grp

    return {
        "account_name":       account.get("account_name") or account.get("name"),
        "account_type":       account.get("account_type") or "",
        "is_group":           _("Да") if is_grp else _("Нет"),
        "category_name":      category_name,
        "activity_type":      activity,
        "direction":          direction,
        "status":             status,
        "account_doc_name":   account.get("name"),
        "category_item_name": item_name,
        "can_assign":         "1" if effective_can_assign else "0",
        "row_type":           "data",
        "_is_group":          is_grp,   # internal flag for JS
    }


def _empty_row(message):
    return {
        "account_name":    message,
        "account_type":    "",
        "is_group":        "",
        "category_name":   "",
        "activity_type":   "",
        "direction":       "",
        "status":          "",
        "account_doc_name": "",
        "category_item_name": "",
        "can_assign":      "0",
        "row_type":        "empty",
    }


def _spacer():
    return {
        "account_name":    "",
        "account_type":    "",
        "is_group":        "",
        "category_name":   "",
        "activity_type":   "",
        "direction":       "",
        "status":          "",
        "account_doc_name": "",
        "category_item_name": "",
        "can_assign":      "0",
        "row_type":        "spacer",
    }


def _summary_row(mapped, unmapped, groups):
    total = mapped + unmapped
    pct   = round((mapped / total * 100), 1) if total else 0.0
    return {
        "account_name":    _(
            "Итого: {0} назначено / {1} не назначено / {2} групп | Покрытие: {3}%"
        ).format(mapped, unmapped, groups, pct),
        "account_type":    "",
        "is_group":        "",
        "category_name":   "",
        "activity_type":   "",
        "direction":       "",
        "status":          "summary",
        "account_doc_name": "",
        "category_item_name": "",
        "can_assign":      "0",
        "row_type":        "summary",
    }


# ---------------------------------------------------------------------------
# QUICK-ASSIGN API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def assign_account_to_category(account_name, category_name,
                                direction_override=None, account_label=None):
    """
    Adds a new row to Cash Flow Categories Item for the given account.

    Guards:
    - Permission check (ASSIGN_ALLOWED_ROLES)
    - Account must exist and not be a group
    - Category must exist
    - Duplicate check: same account in same category → skip with message
    """
    if not _can_assign():
        frappe.throw(_("Недостаточно прав для назначения счёта."),
                     frappe.PermissionError)

    # Validate account
    acc = frappe.get_value(
        "Account", account_name,
        ["name", "is_group", "account_name"],
        as_dict=True,
    )
    if not acc:
        frappe.throw(_("Account not found: {0}").format(account_name))
    if cint(acc.get("is_group")):
        frappe.throw(_("Group accounts cannot be assigned to a category."))

    # Validate category
    if not frappe.db.exists("Cash Flow Categories", category_name):
        frappe.throw(_("Category not found: {0}").format(category_name))

    # Duplicate check
    existing = frappe.db.exists(
        "Cash Flow Categories Item",
        {
            "parent":               category_name,
            "direct_expence_account": account_name,
            "parenttype":           "Cash Flow Categories",
        },
    )
    if existing:
        return {
            "status":  "duplicate",
            "message": _("Счёт уже привязан к этой категории."),
        }

    # Sanitise direction_override
    valid_overrides = {"", "(blank)", "Приход (Inflow)", "Расход (Outflow)"}
    if direction_override not in valid_overrides:
        direction_override = ""
    if direction_override == "(blank)":
        direction_override = ""

    # Append child row
    cat_doc = frappe.get_doc("Cash Flow Categories", category_name)
    cat_doc.append("direct_cash_flow", {
        "direct_expence_account": account_name,
        "account_label":          account_label or "",
        "direction_override":     direction_override or "",
    })
    cat_doc.save(ignore_permissions=False)

    # Invalidate Direct Cash Flow report cache
    _clear_report_cache()

    return {
        "status":  "ok",
        "message": _("Счёт успешно назначен."),
    }


@frappe.whitelist()
def remove_account_from_category(category_item_name):
    """
    Removes a single Cash Flow Categories Item row by its `name`.
    Used from the "Unassign" action in the report.
    """
    if not _can_assign():
        frappe.throw(_("Недостаточно прав для удаления привязки."),
                     frappe.PermissionError)

    if not frappe.db.exists("Cash Flow Categories Item", category_item_name):
        frappe.throw(_("Item not found: {0}").format(category_item_name))

    # Get parent before deleting
    parent_name = frappe.db.get_value(
        "Cash Flow Categories Item", category_item_name, "parent"
    )

    frappe.db.delete("Cash Flow Categories Item", {"name": category_item_name})
    frappe.db.commit()

    _clear_report_cache()

    return {
        "status":  "ok",
        "message": _("Привязка удалена."),
        "parent":  parent_name,
    }


@frappe.whitelist()
def get_categories_for_assign():
    """
    Returns all Cash Flow Categories for the assign dialog dropdown.
    Grouped by activity_type for easier selection.
    """
    return frappe.get_all(
        "Cash Flow Categories",
        fields=["name", "category_name", "activity_type", "is_inflow"],
        order_by="activity_type asc, sort_order asc",
    )


# ---------------------------------------------------------------------------
# CACHE INVALIDATION
# ---------------------------------------------------------------------------

def _clear_report_cache():
    """Invalidates the Direct Cash Flow account_map cache."""
    frappe.cache().delete_value("direct_cash_flow_account_map_v2")
