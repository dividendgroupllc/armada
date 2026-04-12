import frappe
from typing import Optional


def get_bot_token() -> str:
    """Bot tokenni Telegram Bot Settings doctypedan o'qiydi."""
    token = frappe.db.get_single_value("Telegram Bot Settings", "bot_token")

    if not token or set(str(token)) == {"*"}:
        frappe.log_error(
            "Bot token kiritilmagan. Armada > Telegram Bot Settings ga kiring.",
            "Telegram Config",
        )
        raise ValueError("Bot token sozlanmagan")
    return token


def get_admin_chat_ids() -> list[int]:
    """Barcha admin chat ID larini qaytaradi."""
    rows = frappe.get_all(
        "Telegram Admin",
        filters={"parenttype": "Telegram Bot Settings", "parentfield": "admins"},
        fields=["chat_id"],
    )
    result = []
    for row in rows:
        try:
            result.append(int(row.chat_id))
        except (ValueError, TypeError):
            pass
    return result


def is_bot_active() -> bool:
    """Bot faolligini tekshiradi."""
    return bool(frappe.db.get_single_value("Telegram Bot Settings", "is_active"))


def is_admin(chat_id: int) -> bool:
    return chat_id in get_admin_chat_ids()
