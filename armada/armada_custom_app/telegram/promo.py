"""Aksiya (e'lon) ni botga ulangan barcha mijozlarga yuborish."""

import time

import frappe

from armada.armada_custom_app.telegram.config import get_admin_chat_ids
from armada.armada_custom_app.telegram.messages import ADMIN_PROMO_DONE
from armada.armada_custom_app.telegram.sender import copy_message, send_message

# Telegram limiti ~30 xabar/soniya — biroz pastroq tezlikda yuboramiz
_SEND_INTERVAL = 0.05


def get_recipients() -> list[int]:
    """Telegram'ga ulangan faol mijozlar (Customer) chat ID lari (adminlarsiz, takrorsiz)."""
    admins = set(get_admin_chat_ids())
    result = []
    seen = set()
    chat_ids = frappe.get_all(
        "Customer",
        filters=[["telegram_chat_id", "not in", ["", None]], ["disabled", "=", 0]],
        pluck="telegram_chat_id",
    )
    for raw in chat_ids:
        try:
            chat_id = int(raw)
        except (ValueError, TypeError):
            continue
        if chat_id in admins or chat_id in seen:
            continue
        seen.add(chat_id)
        result.append(chat_id)
    return result


def broadcast(admin_chat_id: int, message_id: int) -> None:
    """Admin chatidagi xabarni barcha userlarga nusxalaydi va natijani adminga yuboradi.

    frappe.enqueue orqali "long" navbatda ishlaydi.
    """
    sent = failed = 0
    for chat_id in get_recipients():
        if copy_message(chat_id, admin_chat_id, message_id, log_errors=False):
            sent += 1
        else:
            failed += 1
        time.sleep(_SEND_INTERVAL)

    send_message(admin_chat_id, ADMIN_PROMO_DONE.format(sent=sent, failed=failed))
