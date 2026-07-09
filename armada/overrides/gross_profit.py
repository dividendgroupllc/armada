"""Standart ERPNext "Gross Profit" reportini armada app ichidan kengaytirish.

erpnext yadrosiga (core) tegmaymiz. Buning o'rniga ish vaqtida (runtime)
`erpnext.accounts.report.gross_profit.gross_profit.execute` funksiyasini
o'rab (wrap) qo'yamiz. Shu sababli:

* yangi bench / yangi sayt ochib faqat erpnext o'rnatilsa — Gross Profit
  report asl holatida qoladi (armada o'rnatilmagani uchun patch ishlamaydi);
* qo'shimcha ustunlar faqat group_by = "Customer" bo'lganda va joriy saytda
  armada o'rnatilgan bo'lsa qo'shiladi.

Qo'shiladigan narsa: tanlangan oraliqdan oldingi 2 oyning customer bo'yicha
qty yig'indisi, "Qty" ustunidan oldin (tahlil uchun).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

# Tanlangan oraliq boshlangan oyga nisbatan undan oldingi 2 oy (xronologik).
# Misol: from_date июнь (oy 6) -> апрель (-2) va май (-1).
PRIOR_MONTH_OFFSETS = (-2, -1)

MONTH_LABELS = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

# erpnext'ning asl execute funksiyasiga ishora (apply() da to'ldiriladi).
_original_execute = None


def apply() -> None:
    """erpnext gross_profit modulidagi execute'ni armada versiyasiga almashtiradi.

    Idempotent: takror chaqirilsa qayta o'ramaydi. erpnext hali import
    qilinmagan/mavjud bo'lmagan holatda jimgina o'tib ketadi (report o'shanda
    asl erpnext mantig'i bilan ishlayveradi).
    """
    global _original_execute
    try:
        from erpnext.accounts.report.gross_profit import gross_profit as gp_module
    except Exception:
        return

    if getattr(gp_module, "_armada_customer_patch", False):
        return

    _original_execute = gp_module.execute
    gp_module.execute = execute
    gp_module._armada_customer_patch = True


def ensure_no_duplicate_total() -> None:
    """"Gross Profit" reportida `add_total_row` ni 0 da ushlab turadi.

    erpnext skripti o'z "Total" qatorini qo'shadi; agar report hujjatida
    `add_total_row = 1` bo'lsa, Frappe freymvorki ustiga ikkinchi (dublikat,
    ikki barobar hisoblaydigan) total qatorini qo'shadi. ERPNext bu reportni
    0 bilan tarqatadi. after_migrate hook orqali har bir saytda enforce qilamiz.
    """
    if not frappe.db.exists("Report", "Gross Profit"):
        return
    if frappe.db.get_value("Report", "Gross Profit", "add_total_row"):
        frappe.db.set_value("Report", "Gross Profit", "add_total_row", 0)


def execute(filters: dict[str, Any] | None = None):
    """erpnext Gross Profit execute ustiga o'ralgan versiya."""
    columns, data = _original_execute(filters)

    filters = frappe._dict(filters or {})

    if "armada" not in frappe.get_installed_apps():
        return columns, data

    group_by = (filters.get("group_by") or "").strip()

    # erpnext "Total" qatorida Qty bo'sh qoladi -> qty ustuni bor har qanday
    # group'lashda (Item Code, Customer, Item Group, ...) yig'indi bilan to'ldiramiz.
    # "Invoice" bundan mustasno: unda qatorlar dict va invoice/item darajalari
    # aralashgani uchun yig'indi ikki barobar bo'lib ketadi.
    if group_by and group_by != "Invoice":
        _fill_total_row_qty(columns, data)

    # Oldingi 2 oy ustunlari faqat Customer bo'yicha group qilinganda.
    if group_by != "Customer":
        return columns, data

    periods = _prior_two_months(filters.get("from_date"))
    if not periods:
        return columns, data

    qty_maps = [_customer_qty(filters, period) for period in periods]

    # Oldingi 2 oy ustunlarini "Qty" ustunidan oldin joylashtiramiz.
    qty_index = next(
        (i for i, col in enumerate(columns) if isinstance(col, dict) and col.get("fieldname") == "qty"),
        len(columns),
    )

    columns[qty_index:qty_index] = [
        {
            "label": period["label"],
            "fieldname": period["fieldname"],
            "fieldtype": "Float",
            "precision": 2,
            "width": 130,
        }
        for period in periods
    ]

    for row in data:
        if not isinstance(row, list) or not row:
            continue
        customer = row[0]
        if customer == "Total":
            values = [flt(sum(qty_map.values())) for qty_map in qty_maps]
        else:
            values = [flt(qty_map.get(customer, 0)) for qty_map in qty_maps]
        row[qty_index:qty_index] = values

    return columns, data


def _fill_total_row_qty(columns: list, data: list) -> None:
    """"Total" qatoridagi bo'sh Qty katakchasini qatorlar yig'indisi bilan to'ldiradi.

    Qty ustuni bo'lmagan group'lashlarda (Territory, Project, ...) hech narsa
    qilmaydi. "Invoice" group'lashdagi dict qatorlarga ham tegmaydi.
    """
    qty_index = next(
        (i for i, col in enumerate(columns) if isinstance(col, dict) and col.get("fieldname") == "qty"),
        None,
    )
    if qty_index is None:
        return

    total_qty = sum(
        flt(row[qty_index])
        for row in data
        if isinstance(row, list) and len(row) > qty_index and row and row[0] != "Total"
    )
    for row in data:
        if isinstance(row, list) and row and row[0] == "Total" and len(row) > qty_index:
            if not flt(row[qty_index]):
                row[qty_index] = total_qty


def _prior_two_months(from_date: Any) -> list[dict[str, Any]]:
    if not from_date:
        return []

    start = get_first_day(getdate(from_date))
    periods: list[dict[str, Any]] = []
    for offset in PRIOR_MONTH_OFFSETS:
        month_start = get_first_day(add_months(start, offset))
        month_end = get_last_day(month_start)
        periods.append(
            {
                "label": f"{MONTH_LABELS[month_start.month - 1]} {month_start.year}",
                "fieldname": f"qty_{month_start.strftime('%Y_%m')}",
                "from_date": str(month_start),
                "to_date": str(month_end),
            }
        )
    return periods


def _customer_qty(filters: frappe._dict, period: dict[str, Any]) -> dict[str, float]:
    params: dict[str, Any] = {
        "company": filters.get("company"),
        "from_date": period["from_date"],
        "to_date": period["to_date"],
    }
    item_group_clause = ""
    if filters.get("item_group"):
        item_group_clause = " AND sii.item_group = %(item_group)s"
        params["item_group"] = filters.get("item_group")

    rows = frappe.db.sql(
        f"""
        SELECT
            si.customer AS customer,
            SUM(COALESCE(sii.stock_qty, sii.qty, 0)) AS qty
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
          AND COALESCE(si.is_return, 0) = 0
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {item_group_clause}
        GROUP BY si.customer
        """,
        params,
        as_dict=True,
    )

    return {row.customer: flt(row.qty) for row in rows}
