"""Sales Invoice doc_event: notify Customer on submit."""

import frappe

from armada.armada_custom_app.telegram.keyboards import akt_sverka_keyboard
from armada.armada_custom_app.telegram.messages import SALES_INVOICE_SUBMITTED


def on_submit(doc, method):
    customer = doc.customer
    if not customer:
        return

    chat_id = frappe.db.get_value("Customer", customer, "telegram_chat_id")
    if not chat_id:
        return

    try:
        chat_id = int(chat_id)
    except (ValueError, TypeError):
        return

    text = SALES_INVOICE_SUBMITTED.format(
        name=doc.name,
        grand_total=f"{doc.grand_total:,.2f}",
        currency=doc.currency or "",
        posting_date=doc.posting_date,
        due_date=doc.due_date or doc.posting_date,
    )

    frappe.enqueue(
        "armada.armada_custom_app.telegram.sender.send_message",
        chat_id=chat_id,
        text=text,
        reply_markup=akt_sverka_keyboard(),
        queue="short",
        is_async=True,
    )
