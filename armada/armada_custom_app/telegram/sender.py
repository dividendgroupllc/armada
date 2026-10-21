import json
import frappe
import requests
from typing import Optional

from armada.armada_custom_app.telegram.config import get_bot_token, is_bot_active

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _url(method: str) -> str:
    return _TELEGRAM_API.format(token=get_bot_token(), method=method)


def send_message(
    chat_id: int,
    text: str,
    reply_markup: Optional[dict] = None,
    parse_mode: str = "HTML",
) -> bool:
    """Send a text message to a Telegram chat."""
    if not is_bot_active():
        return False
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(_url("sendMessage"), json=payload, timeout=10)
        if not r.ok:
            frappe.log_error(r.text, f"Telegram sendMessage Error (chat_id={chat_id})")
        return r.ok
    except Exception as e:
        frappe.log_error(str(e), f"Telegram sendMessage Exception (chat_id={chat_id})")
        return False


def copy_message(
    chat_id: int,
    from_chat_id: int,
    message_id: int,
    caption: Optional[str] = None,
    reply_markup: Optional[dict] = None,
    log_errors: bool = True,
) -> bool:
    """Xabarni (matn, rasm, video...) "Forwarded" belgisisiz boshqa chatga nusxalaydi.

    caption berilsa — media xabarning izohi shu matn bilan almashtiriladi.
    """
    if not is_bot_active():
        return False
    payload = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(_url("copyMessage"), json=payload, timeout=10)
        if not r.ok and log_errors:
            frappe.log_error(r.text, f"Telegram copyMessage Error (chat_id={chat_id})")
        return r.ok
    except Exception as e:
        if log_errors:
            frappe.log_error(str(e), f"Telegram copyMessage Exception (chat_id={chat_id})")
        return False


def edit_message_reply_markup(chat_id: int, message_id: int, reply_markup: Optional[dict] = None) -> None:
    """Inline tugmalarni o'zgartiradi (reply_markup=None — tugmalarni olib tashlaydi)."""
    payload = {"chat_id": chat_id, "message_id": message_id}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(_url("editMessageReplyMarkup"), json=payload, timeout=5)
    except Exception:
        pass


def send_document(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str = "",
) -> bool:
    """Send a document (PDF) to a Telegram chat."""
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    files = {"document": (filename, file_bytes, "application/pdf")}

    try:
        r = requests.post(_url("sendDocument"), data=data, files=files, timeout=60)
        if not r.ok:
            frappe.log_error(r.text, f"Telegram sendDocument Error (chat_id={chat_id})")
        return r.ok
    except Exception as e:
        frappe.log_error(str(e), f"Telegram sendDocument Exception (chat_id={chat_id})")
        return False


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Acknowledge an inline button press."""
    try:
        requests.post(
            _url("answerCallbackQuery"),
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def get_me() -> dict:
    """Return bot info (username, id, etc.)."""
    try:
        r = requests.get(_url("getMe"), timeout=5)
        return r.json().get("result", {})
    except Exception:
        return {}


@frappe.whitelist()
def set_webhook(webhook_url: str) -> dict:
    """Register webhook URL with Telegram.

    Call from ERPNext console:
        frappe.call("armada.armada_custom_app.telegram.sender.set_webhook",
                    webhook_url="https://your-server.com/api/method/...")
    """
    try:
        r = requests.post(_url("setWebhook"), json={"url": webhook_url}, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


@frappe.whitelist()
def delete_webhook() -> dict:
    """Remove the registered webhook."""
    try:
        r = requests.post(_url("deleteWebhook"), timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}
