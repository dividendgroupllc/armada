"""Telegram inline and reply keyboard definitions."""


def akt_sverka_keyboard() -> dict:
    """Inline keyboard — choose Akt Sverka period."""
    return {
        "inline_keyboard": [
            [
                {"text": "📅 2 недели",  "callback_data": "aks:2w"},
                {"text": "📅 1 месяц",   "callback_data": "aks:1m"},
            ],
            [
                {"text": "📅 3 месяца",     "callback_data": "aks:3m"},
                {"text": "📅 За всё время", "callback_data": "aks:all"},
            ],
        ]
    }


def main_menu_keyboard() -> dict:
    """Persistent reply keyboard shown to linked customers/suppliers."""
    return {
        "keyboard": [
            [{"text": "📊 Акт Сверки"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


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
