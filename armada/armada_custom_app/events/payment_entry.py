"""Payment Entry doc_events: notify Customer or Supplier on submit/cancel."""

import frappe

from armada.armada_custom_app.telegram.keyboards import akt_sverka_keyboard
from armada.armada_custom_app.telegram.messages import (
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


def on_submit(doc, method):
    chat_id = _get_chat_id(doc.party_type, doc.party)
    if not chat_id:
        return

    currency = doc.paid_from_account_currency or doc.currency or ""
    paid_amount = f"{doc.paid_amount:,.2f}"

    # "Receive" — money coming IN (customer pays us)
    # "Pay"     — money going OUT (we pay supplier)
    if doc.payment_type == "Receive":
        text = PAYMENT_RECEIVED.format(
            name=doc.name,
            paid_amount=paid_amount,
            currency=currency,
            posting_date=doc.posting_date,
        )
    else:
        text = PAYMENT_SENT.format(
            name=doc.name,
            paid_amount=paid_amount,
            currency=currency,
            posting_date=doc.posting_date,
        )

    frappe.enqueue(
        "armada.armada_custom_app.telegram.sender.send_message",
        chat_id=chat_id,
        text=text,
        reply_markup=akt_sverka_keyboard(),
        queue="short",
        is_async=True,
    )


def on_cancel(doc, method):
    chat_id = _get_chat_id(doc.party_type, doc.party)
    if not chat_id:
        return

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
    )
