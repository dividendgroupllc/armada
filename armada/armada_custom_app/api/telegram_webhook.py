"""Telegram webhook endpoint.

Ro'yxatdan o'tish oqimi:
    1. User /start bosadi
    2. Bot telefon raqam so'raydi
    3. User raqam yuboradi
    4. Bot ERPNext da Customer/Supplier ni mobile_no orqali qidiradi
    5. Topilsa — telegram_chat_id saqlanadi, bildirişnomalar shu userga boradi

Webhook ro'yxatdan o'tkazish:
    bench execute armada.armada_custom_app.telegram.sender.set_webhook \
        --kwargs '{"webhook_url": "https://your-erp.com/api/method/armada.armada_custom_app.api.telegram_webhook.handle"}'
"""

import json
import re

import frappe

from armada.armada_custom_app.telegram.config import is_admin
from armada.armada_custom_app.telegram.keyboards import (
    akt_sverka_keyboard,
    admin_menu_keyboard,
    main_menu_keyboard,
)
from armada.armada_custom_app.telegram.messages import (
    ADMIN_BOT_STATUS,
    ADMIN_NO_UNLINKED,
    ADMIN_UNLINKED_LIST,
    ADMIN_WELCOME,
    ALREADY_LINKED,
    ASK_PHONE,
    CHOOSE_PERIOD,
    NOT_LINKED,
    PHONE_NOT_FOUND,
    PHONE_INVALID,
    WELCOME_CUSTOMER,
    WELCOME_SUPPLIER,
)
from armada.armada_custom_app.telegram.sender import answer_callback_query, get_me, send_message

# Cache key prefix — foydalanuvchi holatini saqlash uchun (5 daqiqa)
_STATE_PREFIX = "tg_state:"
_STATE_TTL = 300


@frappe.whitelist(allow_guest=True)
def handle():
    """Telegram har bir update da shu URL ni chaqiradi."""
    raw = frappe.request.data
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        update = json.loads(raw)
    except Exception:
        return {"ok": True}

    if "message" in update:
        _on_message(update["message"])
    elif "callback_query" in update:
        _on_callback(update["callback_query"])

    return {"ok": True}


# ─── Xabar dispatcher ────────────────────────────────────────────────────────

def _on_message(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Admin alohida oqim
    if is_admin(chat_id):
        _admin_message(chat_id, text)
        return

    # /start
    if text.startswith("/start"):
        _cmd_start(chat_id)
        return

    # Akt Sverka tugmasi
    if text == "📊 Акт Сверки":
        if _is_linked(chat_id):
            send_message(chat_id, CHOOSE_PERIOD, reply_markup=akt_sverka_keyboard())
        else:
            send_message(chat_id, NOT_LINKED)
        return

    # Telefon raqam kutilayotgan holat
    state = _get_state(chat_id)
    if state == "awaiting_phone":
        _handle_phone_input(chat_id, text)
        return

    # Qolgan hollar
    if _is_linked(chat_id):
        send_message(
            chat_id,
            "Нажмите кнопку <b>📊 Акт Сверки</b> для запроса документа.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        send_message(chat_id, NOT_LINKED)


# ─── Callback dispatcher ─────────────────────────────────────────────────────

def _on_callback(callback_query: dict) -> None:
    chat_id = callback_query["from"]["id"]
    data = callback_query.get("data", "")
    cq_id = callback_query["id"]

    if data.startswith("aks:"):
        period_code = data.split(":", 1)[1]
        frappe.enqueue(
            "armada.armada_custom_app.telegram.pdf_handler.handle_akt_sverka_callback",
            chat_id=chat_id,
            period_code=period_code,
            callback_query_id=cq_id,
            queue="long",
            is_async=True,
        )
        return

    answer_callback_query(cq_id)


# ─── /start ──────────────────────────────────────────────────────────────────

def _cmd_start(chat_id: int) -> None:
    # Allaqachon ulangan?
    if _is_linked(chat_id):
        send_message(chat_id, ALREADY_LINKED, reply_markup=main_menu_keyboard())
        return

    # Telefon raqam so'ra
    _set_state(chat_id, "awaiting_phone")
    send_message(chat_id, ASK_PHONE)


# ─── Telefon raqam orqali ro'yxatdan o'tish ──────────────────────────────────

def _handle_phone_input(chat_id: int, text: str) -> None:
    """User yuborgan raqamni Customer/Supplier da qidiradi."""
    phone = _normalize_phone(text)

    if not phone:
        send_message(chat_id, PHONE_INVALID)
        return

    result = _find_party_by_phone(phone)

    if not result:
        send_message(chat_id, PHONE_NOT_FOUND)
        # Holatni saqlab qo'yamiz — user boshqa raqam urinib ko'rishi mumkin
        return

    party_type, party_name, display_name = result

    # telegram_chat_id saqla
    frappe.db.set_value(
        party_type,
        party_name,
        "telegram_chat_id",
        str(chat_id),
    )
    frappe.db.commit()

    # Holatni tozala
    _clear_state(chat_id)

    if party_type == "Customer":
        msg = WELCOME_CUSTOMER.format(name=display_name)
    else:
        msg = WELCOME_SUPPLIER.format(name=display_name)

    send_message(chat_id, msg, reply_markup=main_menu_keyboard())


def _normalize_phone(raw: str) -> str:
    """Telefon raqamni faqat raqamlarga kamaytiradi.

    +998 90 123 45 67  →  998901234567
    0901234567         →  998901234567  (O'zbekiston prefiksi)
    901234567          →  998901234567
    """
    digits = re.sub(r"\D", "", raw)

    # 9 raqam — faqat operator kodi + raqam
    if len(digits) == 9:
        digits = "998" + digits
    # 0 bilan boshlangan 10 raqam — 0 ni 998 bilan almashtir
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "998" + digits[1:]

    # 12 raqam — to'liq (998XXXXXXXXX)
    if len(digits) == 12 and digits.startswith("998"):
        return digits

    # Boshqa formatlar ham qidiriladi
    if len(digits) >= 7:
        return digits

    return ""


def _find_party_by_phone(phone: str):
    """Customer va Supplier ni contact_number orqali qidiradi.

    Raqam turli formatlarda kiritilishi mumkin,
    shuning uchun qisman mos kelishni ham tekshiramiz.
    """
    # To'liq mos kelish
    for doctype, name_field in [("Customer", "customer_name"), ("Supplier", "supplier_name")]:
        row = frappe.db.get_value(
            doctype,
            {"contact_number": phone},
            ["name", name_field],
            as_dict=True,
        )
        if row:
            return doctype, row.name, row[name_field]

    # Oxirgi 9 raqam bilan qisman mos kelish (format farqi uchun)
    last9 = phone[-9:] if len(phone) >= 9 else phone
    for doctype, name_field in [("Customer", "customer_name"), ("Supplier", "supplier_name")]:
        rows = frappe.db.get_all(
            doctype,
            filters=[["contact_number", "like", f"%{last9}"]],
            fields=["name", name_field],
            limit=1,
        )
        if rows:
            row = rows[0]
            return doctype, row.name, row[name_field]

    return None


# ─── Admin handlers ───────────────────────────────────────────────────────────

def _admin_message(chat_id: int, text: str) -> None:
    if text in ("/start", "/admin"):
        send_message(chat_id, ADMIN_WELCOME, reply_markup=admin_menu_keyboard())
        return

    if text == "👥 Контрагенты без Telegram":
        _admin_unlinked(chat_id)
        return

    if text == "ℹ️ Статус бота":
        _admin_status(chat_id)
        return

    send_message(chat_id, ADMIN_WELCOME, reply_markup=admin_menu_keyboard())


def _admin_unlinked(chat_id: int) -> None:
    lines = []

    customers = frappe.db.get_all(
        "Customer",
        filters=[["telegram_chat_id", "in", ["", None]]],
        fields=["customer_name", "contact_number"],
        limit=30,
    )
    for c in customers:
        phone = c.contact_number or "—"
        lines.append(f"👤 {c.customer_name}  <code>{phone}</code>")

    suppliers = frappe.db.get_all(
        "Supplier",
        filters=[["telegram_chat_id", "in", ["", None]]],
        fields=["supplier_name", "contact_number"],
        limit=30,
    )
    for s in suppliers:
        phone = s.contact_number or "—"
        lines.append(f"🏭 {s.supplier_name}  <code>{phone}</code>")

    if not lines:
        send_message(chat_id, ADMIN_NO_UNLINKED)
        return

    send_message(
        chat_id,
        ADMIN_UNLINKED_LIST.format(count=len(lines), list="\n".join(lines)),
    )


def _admin_status(chat_id: int) -> None:
    bot_info = get_me()
    customers = frappe.db.count(
        "Customer", filters=[["telegram_chat_id", "not in", ["", None]]]
    )
    suppliers = frappe.db.count(
        "Supplier", filters=[["telegram_chat_id", "not in", ["", None]]]
    )
    send_message(
        chat_id,
        ADMIN_BOT_STATUS.format(
            username=bot_info.get("username", "—"),
            bot_id=bot_info.get("id", "—"),
            customers=customers,
            suppliers=suppliers,
        ),
    )


# ─── Holat (state) boshqaruvi — Redis cache ───────────────────────────────────

def _set_state(chat_id: int, state: str) -> None:
    frappe.cache().set_value(f"{_STATE_PREFIX}{chat_id}", state, expires_in_sec=_STATE_TTL)


def _get_state(chat_id: int) -> str:
    return frappe.cache().get_value(f"{_STATE_PREFIX}{chat_id}") or ""


def _clear_state(chat_id: int) -> None:
    frappe.cache().delete_value(f"{_STATE_PREFIX}{chat_id}")


# ─── DB yordamchi funksiyalar ─────────────────────────────────────────────────

def _is_linked(chat_id: int) -> bool:
    return _find_party_by_chat_id(str(chat_id)) is not None


def _find_party_by_chat_id(chat_id_str: str):
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
