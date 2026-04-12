import frappe
from typing import Optional


def get_bot_token() -> str:
    """Read bot token from site_config.json.

    Add to your site_config.json:
        "telegram_bot_token": "123456:ABC-DEF..."
    """
    token = frappe.conf.get("telegram_bot_token")
    if not token:
        frappe.log_error(
            "telegram_bot_token not configured in site_config.json",
            "Telegram Config",
        )
        raise ValueError("telegram_bot_token not set in site_config.json")
    return token


def get_admin_chat_id() -> Optional[int]:
    """Admin Telegram chat ID (Abdulloh aka).

    Add to your site_config.json:
        "telegram_admin_chat_id": 123456789
    """
    chat_id = frappe.conf.get("telegram_admin_chat_id")
    return int(chat_id) if chat_id else None


def is_admin(chat_id: int) -> bool:
    admin = get_admin_chat_id()
    return admin is not None and chat_id == admin
