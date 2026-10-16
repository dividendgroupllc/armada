"""Sales Invoice doc_event: notify Customer on submit."""

import frappe

from armada.armada_custom_app.telegram.formatting import (
    balance_line,
    fmt_amount,
    fmt_date,
    fmt_qty,
    h,
    party_balance,
)
from armada.armada_custom_app.telegram.keyboards import remove_keyboard
from armada.armada_custom_app.telegram.messages import (
    SALES_INVOICE_COMMENT,
    SALES_INVOICE_ITEM,
    SALES_INVOICE_SUBMITTED,
)


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

    items = "\n\n".join(
        SALES_INVOICE_ITEM.format(
            item_name=h(row.item_name or row.item_code),
            qty=fmt_qty(row.qty, row.uom),
            rate=fmt_amount(row.rate, doc.currency),
        )
        for row in doc.items
    )

    comment = _sales_order_comment(doc)
    if comment:
        items += "\n\n" + SALES_INVOICE_COMMENT.format(comment=h(comment))

    # GL yozuvlari submit paytida allaqachon yaratilgan — saldo shu hujjatni ham o'z ichiga oladi
    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    balance = party_balance("Customer", customer, doc.company)

    text = SALES_INVOICE_SUBMITTED.format(
        posting_date=fmt_date(doc.posting_date),
        name=h(doc.name),
        customer=h(doc.customer_name or customer),
        title="↩️ Qaytarish tafsiloti:" if doc.is_return else "🤝 Sotuv tafsiloti:",
        items=items,
        grand_total=fmt_amount(abs(doc.grand_total), doc.currency),
        balance_line=balance_line(balance, company_currency),
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


def _sales_order_comment(doc) -> str:
    """Hujjat bog'langan Sales Order(lar)ning custom_komment maydoni."""
    sales_orders = list(dict.fromkeys(row.sales_order for row in doc.items if row.sales_order))
    if not sales_orders:
        return ""
    comments = frappe.get_all(
        "Sales Order",
        filters={"name": ["in", sales_orders]},
        pluck="custom_komment",
    )
    return "; ".join(dict.fromkeys(c.strip() for c in comments if c and c.strip()))
