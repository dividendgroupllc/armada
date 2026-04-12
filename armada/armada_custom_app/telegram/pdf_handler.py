"""Akt Sverka PDF generation and delivery via Telegram."""

import base64
from datetime import date
from typing import Optional, Tuple

import frappe
from dateutil.relativedelta import relativedelta

from armada.armada_custom_app.telegram.sender import send_document, send_message, answer_callback_query
from armada.armada_custom_app.telegram.messages import (
    AKT_SVERKA_GENERATING,
    AKT_SVERKA_CAPTION,
    AKT_SVERKA_EMPTY,
    AKT_SVERKA_ERROR,
    PERIOD_LABELS,
)


def _date_range(period_code: str) -> Tuple[str, str]:
    today = date.today()
    if period_code == "2w":
        from_date = today - relativedelta(weeks=2)
    elif period_code == "1m":
        from_date = today - relativedelta(months=1)
    elif period_code == "3m":
        from_date = today - relativedelta(months=3)
    else:  # "all"
        from_date = date(2020, 1, 1)
    return str(from_date), str(today)


def find_party_by_chat_id(chat_id: int) -> Optional[Tuple[str, str, str]]:
    """Return (party_type, name, display_name) for a given chat_id, or None."""
    chat_id_str = str(chat_id)

    row = frappe.db.get_value(
        "Customer",
        {"telegram_chat_id": chat_id_str},
        ["name", "customer_name"],
        as_dict=True,
    )
    if row:
        return "Customer", row.name, row.customer_name

    row = frappe.db.get_value(
        "Supplier",
        {"telegram_chat_id": chat_id_str},
        ["name", "supplier_name"],
        as_dict=True,
    )
    if row:
        return "Supplier", row.name, row.supplier_name

    return None


def handle_akt_sverka_callback(
    chat_id: int,
    period_code: str,
    callback_query_id: str,
) -> None:
    """Called via frappe.enqueue when user presses a period button.

    Generates Akt Sverka PDF and sends it back to the user.
    """
    answer_callback_query(callback_query_id, "Формирую Акт Сверки...")
    send_message(chat_id, AKT_SVERKA_GENERATING)

    party = find_party_by_chat_id(chat_id)
    if not party:
        send_message(chat_id, "❌ Аккаунт не найден. Обратитесь к менеджеру.")
        return

    party_type, party_name, party_display = party
    from_date, to_date = _date_range(period_code)

    filters = {
        "from_date": from_date,
        "to_date": to_date,
        "party_type": party_type,
        "party": party_name,
    }

    try:
        from armada.armada_custom_app.report.akt_sverka.akt_sverka import (
            generate_akt_sverka_pdf,
        )

        pdf_b64 = generate_akt_sverka_pdf(filters)
        pdf_bytes = base64.b64decode(pdf_b64)
    except Exception as e:
        frappe.log_error(str(e), "Akt Sverka PDF Generation Error")
        send_message(chat_id, AKT_SVERKA_ERROR)
        return

    # Treat a very small file as "no data" (wkhtmltopdf still produces ~3 KB)
    if not pdf_bytes or len(pdf_bytes) < 2_000:
        send_message(chat_id, AKT_SVERKA_EMPTY)
        return

    period_label = PERIOD_LABELS.get(period_code, period_code)
    caption = AKT_SVERKA_CAPTION.format(
        period_label=period_label,
        party_name=party_display or party_name,
    )
    safe_name = (party_name[:20]).replace(" ", "_")
    filename = f"akt_sverka_{period_code}_{safe_name}.pdf"

    send_document(chat_id, pdf_bytes, filename, caption)
