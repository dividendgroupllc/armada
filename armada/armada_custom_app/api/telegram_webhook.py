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
from html import escape

import frappe

from armada.armada_custom_app.telegram.config import get_admin_chat_ids, is_admin
from armada.armada_custom_app.telegram.keyboards import (
    BTN_CANCEL,
    BTN_FEEDBACK,
    BTN_PROMO,
    BTN_STATUS,
    BTN_UNLINKED,
    CB_PROMO_CANCEL,
    CB_PROMO_SEND,
    admin_menu_keyboard,
    cancel_keyboard,
    promo_confirm_keyboard,
    user_menu_keyboard,
)
from armada.armada_custom_app.telegram.messages import (
    ADMIN_BOT_STATUS,
    ADMIN_CANCELLED,
    ADMIN_NO_UNLINKED,
    ADMIN_PROMO_ASK,
    ADMIN_PROMO_CANCELLED,
    ADMIN_PROMO_CONFIRM,
    ADMIN_PROMO_NO_USERS,
    ADMIN_PROMO_STARTED,
    ADMIN_REPLY_FAILED,
    ADMIN_REPLY_SENT,
    ADMIN_REPLY_UNKNOWN,
    ADMIN_UNLINKED_LIST,
    ADMIN_WELCOME,
    ALREADY_LINKED,
    ASK_PHONE,
    FEEDBACK_ASK,
    FEEDBACK_CANCELLED,
    FEEDBACK_RECEIVED,
    FEEDBACK_REPLY_TO_USER,
    FEEDBACK_TO_ADMIN,
    FEEDBACK_UNSUPPORTED,
    NOT_LINKED,
    PHONE_NOT_FOUND,
    PHONE_INVALID,
    WELCOME_CUSTOMER,
    WELCOME_SUPPLIER,
)
from armada.armada_custom_app.telegram.promo import get_recipients
from armada.armada_custom_app.telegram.sender import (
    answer_callback_query,
    copy_message,
    edit_message_reply_markup,
    get_me,
    send_message,
)

# Cache key prefix — foydalanuvchi holatini saqlash uchun (5 daqiqa)
_STATE_PREFIX = "tg_state:"
_STATE_TTL = 300
# Murojaat/aksiya matnini yozish uchun ko'proq vaqt beriladi
_INPUT_TTL = 900

_ST_FEEDBACK = "awaiting_feedback"
_ST_PROMO = "awaiting_promo"

# Albom (bir nechta rasm) bitta murojaatga biriktiriladi
_MEDIA_GROUP_PREFIX = "tg_mg:"
_MEDIA_GROUP_TTL = 120
# Aksiya tasdiqlash tugmasini ikki marta bosishdan himoya
_PROMO_DONE_PREFIX = "tg_promo_sent:"

# Admin xabaridagi murojaat raqami ("🆔 MRJ-00001")
_FEEDBACK_ID_RE = re.compile(r"MRJ-\d+")

# Izoh (caption) qo'yish mumkin bo'lgan media turlari
_CAPTION_TYPES = ("photo", "video", "document", "audio", "voice", "animation")
_TEXT_LIMIT = 3500
_CAPTION_LIMIT = 700


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

    process_update(update)
    return {"ok": True}


def process_update(update: dict) -> None:
    """Bitta Telegram update'ni qayta ishlaydi (webhook va lokal polling uchun umumiy)."""
    if "message" in update:
        _on_message(update["message"])
    elif "callback_query" in update:
        _on_callback(update["callback_query"])


# ─── Xabar dispatcher ────────────────────────────────────────────────────────

def _on_message(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Admin alohida oqim
    if is_admin(chat_id):
        _admin_message(message)
        return

    # /start
    if text.startswith("/start"):
        _cmd_start(chat_id)
        return

    # Telefon raqam kutilayotgan holat
    state = _get_state(chat_id)
    if state == "awaiting_phone":
        _handle_phone_input(chat_id, text)
        return

    party = _find_party_by_chat_id(str(chat_id))
    if not party:
        send_message(chat_id, NOT_LINKED)
        return

    _user_message(message, party)


# ─── Callback dispatcher ─────────────────────────────────────────────────────

def _on_callback(callback_query: dict) -> None:
    cq_id = callback_query["id"]
    data = callback_query.get("data") or ""
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")

    if chat_id and is_admin(chat_id) and data.startswith("promo:"):
        _admin_promo_callback(cq_id, chat_id, message["message_id"], data)
        return

    # Eski xabarlardagi "aks:*" (Akt Sverka) tugmalari endi ishlamaydi
    answer_callback_query(cq_id)


# ─── /start ──────────────────────────────────────────────────────────────────

def _cmd_start(chat_id: int) -> None:
    # Allaqachon ulangan?
    if _is_linked(chat_id):
        _clear_state(chat_id)
        send_message(chat_id, ALREADY_LINKED, reply_markup=user_menu_keyboard())
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

    send_message(chat_id, msg, reply_markup=user_menu_keyboard())


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


# ─── Muammo va takliflar (ulangan user) ─────────────────────────────────────

def _user_message(message: dict, party: tuple) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text == BTN_FEEDBACK:
        _set_state(chat_id, _ST_FEEDBACK, _INPUT_TTL)
        send_message(chat_id, FEEDBACK_ASK, reply_markup=cancel_keyboard())
        return

    if text == BTN_CANCEL:
        _clear_state(chat_id)
        send_message(chat_id, FEEDBACK_CANCELLED, reply_markup=user_menu_keyboard())
        return

    if _get_state(chat_id) == _ST_FEEDBACK:
        _handle_feedback(message, party)
        return

    # Albomning qolgan rasmlari — oldingi murojaatga qo'shiladi
    group_id = message.get("media_group_id")
    feedback_name = group_id and frappe.cache().get_value(f"{_MEDIA_GROUP_PREFIX}{group_id}", expires=True)
    if feedback_name:
        _forward_feedback_to_admins(message, feedback_name, party)
        return

    send_message(chat_id, ALREADY_LINKED, reply_markup=user_menu_keyboard())


def _handle_feedback(message: dict, party: tuple) -> None:
    chat_id = message["chat"]["id"]
    body = _message_body(message)
    if body is None:
        send_message(chat_id, FEEDBACK_UNSUPPORTED, reply_markup=cancel_keyboard())
        return

    party_type, party_name, display_name = party
    doc = frappe.get_doc({
        "doctype": "Telegram Murojaat",
        "chat_id": str(chat_id),
        "party_type": party_type,
        "party": party_name,
        "party_name": display_name,
        "message": body or "[media]",
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    _clear_state(chat_id)
    group_id = message.get("media_group_id")
    if group_id:
        frappe.cache().set_value(
            f"{_MEDIA_GROUP_PREFIX}{group_id}", doc.name, expires_in_sec=_MEDIA_GROUP_TTL
        )

    _forward_feedback_to_admins(message, doc.name, party)
    send_message(
        chat_id,
        FEEDBACK_RECEIVED.format(name=doc.name),
        reply_markup=user_menu_keyboard(),
    )


def _forward_feedback_to_admins(message: dict, feedback_name: str, party: tuple) -> None:
    party_type, party_name, display_name = party
    phone = frappe.db.get_value(party_type, party_name, "contact_number") or "—"
    template = FEEDBACK_TO_ADMIN.format(
        name=feedback_name,
        party_label="Mijoz" if party_type == "Customer" else "Yetkazib beruvchi",
        party_name=escape(display_name or party_name),
        phone=escape(phone),
        body="{body}",
    )
    for admin_chat_id in get_admin_chat_ids():
        _relay(admin_chat_id, message, template)


# ─── Admin handlers ───────────────────────────────────────────────────────────

def _admin_message(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text in ("/start", "/admin"):
        _clear_state(chat_id)
        send_message(chat_id, ADMIN_WELCOME, reply_markup=admin_menu_keyboard())
        return

    if text == BTN_CANCEL:
        _clear_state(chat_id)
        send_message(chat_id, ADMIN_CANCELLED, reply_markup=admin_menu_keyboard())
        return

    # Murojaatga Reply — javob userga yuboriladi
    reply_to = message.get("reply_to_message")
    if reply_to and _feedback_id(reply_to):
        _admin_reply(message, _feedback_id(reply_to))
        return

    if _get_state(chat_id) == _ST_PROMO:
        _admin_promo_preview(message)
        return

    if text == BTN_PROMO:
        _set_state(chat_id, _ST_PROMO, _INPUT_TTL)
        send_message(chat_id, ADMIN_PROMO_ASK, reply_markup=cancel_keyboard())
        return

    if reply_to:
        send_message(chat_id, ADMIN_REPLY_UNKNOWN)
        return

    if text == BTN_UNLINKED:
        _admin_unlinked(chat_id)
        return

    if text == BTN_STATUS:
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


def _admin_reply(message: dict, feedback_name: str) -> None:
    chat_id = message["chat"]["id"]
    doc = frappe.db.get_value(
        "Telegram Murojaat", feedback_name, ["name", "chat_id", "party_name", "reply"], as_dict=True
    )
    if not doc or not doc.chat_id:
        send_message(chat_id, ADMIN_REPLY_UNKNOWN)
        return

    if not _relay(int(doc.chat_id), message, FEEDBACK_REPLY_TO_USER):
        send_message(chat_id, ADMIN_REPLY_FAILED)
        return

    admin_name = frappe.db.get_value(
        "Telegram Admin",
        {"parenttype": "Telegram Bot Settings", "chat_id": str(chat_id)},
        "name_label",
    )
    reply = _message_body(message) or "[media]"
    frappe.db.set_value(
        "Telegram Murojaat",
        doc.name,
        {
            "status": "Javob berildi",
            "reply": f"{doc.reply}\n\n{reply}" if doc.reply else reply,
            "replied_by": admin_name or str(chat_id),
        },
    )
    frappe.db.commit()
    send_message(chat_id, ADMIN_REPLY_SENT.format(party_name=escape(doc.party_name or "")))


def _admin_promo_preview(message: dict) -> None:
    chat_id = message["chat"]["id"]
    _clear_state(chat_id)

    if _message_body(message) is None:
        send_message(chat_id, FEEDBACK_UNSUPPORTED, reply_markup=admin_menu_keyboard())
        return

    count = len(get_recipients())
    if not count:
        send_message(chat_id, ADMIN_PROMO_NO_USERS, reply_markup=admin_menu_keyboard())
        return

    # Reply klaviaturani menyuga qaytaramiz, so'ng inline tasdiqlash
    send_message(chat_id, "👇", reply_markup=admin_menu_keyboard())
    send_message(
        chat_id,
        ADMIN_PROMO_CONFIRM.format(count=count),
        reply_markup=promo_confirm_keyboard(message["message_id"]),
    )


def _admin_promo_callback(cq_id: str, chat_id: int, confirm_message_id: int, data: str) -> None:
    edit_message_reply_markup(chat_id, confirm_message_id)

    if data == CB_PROMO_CANCEL:
        answer_callback_query(cq_id)
        send_message(chat_id, ADMIN_PROMO_CANCELLED)
        return

    promo_message_id = int(data.removeprefix(CB_PROMO_SEND))
    done_key = f"{_PROMO_DONE_PREFIX}{chat_id}:{promo_message_id}"
    if frappe.cache().get_value(done_key, expires=True):
        answer_callback_query(cq_id, "Allaqachon yuborilgan")
        return
    frappe.cache().set_value(done_key, 1, expires_in_sec=86400)

    answer_callback_query(cq_id)
    send_message(chat_id, ADMIN_PROMO_STARTED.format(count=len(get_recipients())))
    frappe.enqueue(
        "armada.armada_custom_app.telegram.promo.broadcast",
        admin_chat_id=chat_id,
        message_id=promo_message_id,
        queue="long",
        timeout=3600,
    )


# ─── Xabar nusxalash yordamchilari ───────────────────────────────────────────

def _message_body(message: dict):
    """Xabar matni yoki media izohi. Qo'llab-quvvatlanmaydigan tur bo'lsa — None."""
    if message.get("text"):
        return message["text"]
    if any(k in message for k in _CAPTION_TYPES):
        return message.get("caption") or ""
    return None


def _relay(to_chat_id: int, message: dict, template: str) -> bool:
    """Xabarni sarlavha (template, "{body}" joyi bilan) qo'shib boshqa chatga yuboradi.

    Matn — send_message, media — copy_message (izohi sarlavha bilan almashtiriladi).
    """
    if message.get("text"):
        body = escape(message["text"][:_TEXT_LIMIT])
        return send_message(to_chat_id, template.format(body=body))

    from_chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    if any(k in message for k in _CAPTION_TYPES):
        body = escape((message.get("caption") or "📎")[:_CAPTION_LIMIT])
        return copy_message(to_chat_id, from_chat_id, message_id, caption=template.format(body=body))

    # Stiker va h.k. — izoh qo'yib bo'lmaydi, sarlavha alohida ketadi
    send_message(to_chat_id, template.format(body="📎"))
    return copy_message(to_chat_id, from_chat_id, message_id)


def _feedback_id(message: dict):
    match = _FEEDBACK_ID_RE.search(message.get("text") or message.get("caption") or "")
    return match.group(0) if match else None


# ─── Holat (state) boshqaruvi — Redis cache ───────────────────────────────────

def _set_state(chat_id: int, state: str, ttl: int = _STATE_TTL) -> None:
    frappe.cache().set_value(f"{_STATE_PREFIX}{chat_id}", state, expires_in_sec=ttl)


def _get_state(chat_id: int) -> str:
    return frappe.cache().get_value(f"{_STATE_PREFIX}{chat_id}", expires=True) or ""


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
