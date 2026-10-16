"""Payment Entry doc_events: notify Customer or Supplier on submit/cancel."""

import frappe

from armada.armada_custom_app.telegram.formatting import (
    balance_line,
    fmt_amount,
    fmt_date,
    h,
    party_balance,
)
from armada.armada_custom_app.telegram.keyboards import remove_keyboard
from armada.armada_custom_app.telegram.messages import (
    CUSTOMER_PAYMENT,
    PAYMENT_RECEIVED,
    PAYMENT_SENT,
    PAYMENT_CANCELLED,
)


def _get_chat_id(party_type: str, party: str):
    if party_type not in ("Customer", "Supplier") or not party:
        return None
    raw = frappe.db.get_value(party_type, party, "telegram_chat_id")
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _customer_text(doc, title: str, amount_label: str) -> str:
    # Mijoz hisobi valyutasi: Receive'da paid_from, Pay'da paid_to
    if doc.payment_type == "Receive":
        currency = doc.paid_from_account_currency
    else:
        currency = doc.paid_to_account_currency
    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    balance = party_balance("Customer", doc.party, doc.company)

    return CUSTOMER_PAYMENT.format(
        posting_date=fmt_date(doc.posting_date),
        name=h(doc.name),
        customer=h(doc.party_name or doc.party),
        title=title,
        amount_label=amount_label,
        amount=fmt_amount(doc.paid_amount, currency or company_currency),
        balance_line=balance_line(balance, company_currency),
    )


def on_submit(doc, method):
    chat_id = _get_chat_id(doc.party_type, doc.party)
    if not chat_id:
        return

    if doc.party_type == "Customer":
        if doc.payment_type == "Receive":
            text = _customer_text(doc, "💵 To'lov qabul qilindi:", "To'langan summa")
        else:
            text = _customer_text(doc, "💸 Pul qaytarildi:", "Qaytarilgan summa")
    else:
        currency = doc.paid_from_account_currency or doc.currency or ""
        template = PAYMENT_RECEIVED if doc.payment_type == "Receive" else PAYMENT_SENT
        text = template.format(
            name=doc.name,
            paid_amount=f"{doc.paid_amount:,.2f}",
            currency=currency,
            posting_date=doc.posting_date,
        )

    frappe.enqueue(
        "armada.armada_custom_app.telegram.sender.send_message",
        chat_id=chat_id,
        text=text,
        reply_markup=remove_keyboard(),
        queue="short",
        is_async=True,
        enqueue_after_commit=True,
    )


def on_cancel(doc, method):
    chat_id = _get_chat_id(doc.party_type, doc.party)
    if not chat_id:
        return

    if doc.party_type == "Customer":
        text = _customer_text(doc, "❌ To'lov bekor qilindi:", "Summa")
    else:
        currency = doc.paid_from_account_currency or doc.currency or ""
        text = PAYMENT_CANCELLED.format(
            name=doc.name,
            paid_amount=f"{doc.paid_amount:,.2f}",
            currency=currency,
        )

    frappe.enqueue(
        "armada.armada_custom_app.telegram.sender.send_message",
        chat_id=chat_id,
        text=text,
        queue="short",
        is_async=True,
        enqueue_after_commit=True,
    )
