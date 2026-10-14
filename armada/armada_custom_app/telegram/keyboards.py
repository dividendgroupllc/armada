"""Telegram reply keyboard definitions."""


def remove_keyboard() -> dict:
    """Eski "📊 Акт Сверки" reply-klaviaturasini mijoz ekranidan olib tashlaydi."""
    return {"remove_keyboard": True}


def admin_menu_keyboard() -> dict:
    """Persistent reply keyboard for admin (Abdulloh aka)."""
    return {
        "keyboard": [
            [{"text": "👥 Контрагенты без Telegram"}],
            [{"text": "ℹ️ Статус бота"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }
