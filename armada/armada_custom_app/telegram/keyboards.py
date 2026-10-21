"""Telegram reply keyboard definitions."""

BTN_UNLINKED = "👥 Telegram'siz kontragentlar"
BTN_STATUS = "ℹ️ Bot holati"
BTN_PROMO = "📢 Aksiyalar"
BTN_FEEDBACK = "💬 Muammo va takliflar"
BTN_CANCEL = "❌ Bekor qilish"

# Inline tugmalar callback_data prefiksi
CB_PROMO_SEND = "promo:send:"
CB_PROMO_CANCEL = "promo:cancel"


def remove_keyboard() -> dict:
    """Eski "📊 Акт Сверки" reply-klaviaturasini mijoz ekranidan olib tashlaydi."""
    return {"remove_keyboard": True}


def user_menu_keyboard() -> dict:
    """Ulangan mijoz/yetkazib beruvchi uchun doimiy menyu."""
    return {
        "keyboard": [[{"text": BTN_FEEDBACK}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def cancel_keyboard() -> dict:
    """Matn kutilayotgan paytda faqat "Bekor qilish" tugmasi."""
    return {
        "keyboard": [[{"text": BTN_CANCEL}]],
        "resize_keyboard": True,
    }


def admin_menu_keyboard() -> dict:
    """Persistent reply keyboard for admin (Abdulloh aka)."""
    return {
        "keyboard": [
            [{"text": BTN_PROMO}],
            [{"text": BTN_UNLINKED}],
            [{"text": BTN_STATUS}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def promo_confirm_keyboard(message_id: int) -> dict:
    """Aksiyani barcha userlarga yuborishni tasdiqlash (inline)."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Yuborish", "callback_data": f"{CB_PROMO_SEND}{message_id}"},
            {"text": BTN_CANCEL, "callback_data": CB_PROMO_CANCEL},
        ]]
    }
