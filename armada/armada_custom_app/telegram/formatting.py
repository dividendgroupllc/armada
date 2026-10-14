"""Mijozga boradigan bildirishnomalar uchun formatlash yordamchilari."""

from html import escape

import frappe
from frappe.utils import flt, getdate

_UOM_LABELS = {
    "ШТ": "dona",
    "Nos": "dona",
    "КГ": "kg",
    "М": "metr",
}


def fmt_amount(value, currency: str) -> str:
    """70.0 → '70 $', 1250.5 → '1 250.50 $'."""
    text = f"{abs(flt(value, 2)):,.2f}".removesuffix(".00").replace(",", " ")
    if flt(value, 2) < 0:
        text = "-" + text
    symbol = frappe.db.get_value("Currency", currency, "symbol") if currency else ""
    return f"{text} {symbol or currency or ''}".strip()


def fmt_qty(value, uom: str) -> str:
    qty = f"{abs(flt(value, 3)):,.3f}".rstrip("0").rstrip(".").replace(",", " ")
    return f"{qty} {_UOM_LABELS.get(uom, uom or '')}".strip()


def fmt_date(value) -> str:
    return getdate(value).strftime("%d.%m.%Y")


def h(value) -> str:
    """Telegram HTML parse_mode uchun matnni xavfsiz qiladi."""
    return escape(str(value or ""), quote=False)


def party_balance(party_type: str, party: str, company: str) -> float:
    """Kontragentning joriy saldosi (company valyutasida).

    Customer uchun musbat qiymat — mijoz bizga qarzdor.
    """
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND company = %s AND is_cancelled = 0
        """,
        (party_type, party, company),
    )
    return flt(result[0][0], 2)


def balance_line(balance: float, currency: str) -> str:
    if balance < 0:
        return f"📊 Avansingiz: {fmt_amount(-balance, currency)}"
    return f"📊 Joriy qarzingiz: {fmt_amount(balance, currency)}"
