"""Telegram reply keyboard definitions."""

BTN_UNLINKED = "👥 Telegram'siz kontragentlar"
BTN_STATUS = "ℹ️ Bot holati"


def remove_keyboard() -> dict:
    """Eski "📊 Акт Сверки" reply-klaviaturasini mijoz ekranidan olib tashlaydi."""
    return {"remove_keyboard": True}


def admin_menu_keyboard() -> dict:
    """Persistent reply keyboard for admin (Abdulloh aka)."""
    return {
        "keyboard": [
            [{"text": BTN_UNLINKED}],
            [{"text": BTN_STATUS}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }
