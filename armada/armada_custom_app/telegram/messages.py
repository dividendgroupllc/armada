"""Russian message templates for all bot scenarios."""

# ─── Onboarding ───────────────────────────────────────────────────────────────

WELCOME_CUSTOMER = (
    "👋 Добро пожаловать, <b>{name}</b>!\n\n"
    "Вы успешно подключились как <b>Клиент</b>.\n\n"
    "Вы будете получать уведомления о:\n"
    "• 📄 Выставленных счетах-фактурах\n"
    "• 💳 Поступлениях платежей"
)

WELCOME_SUPPLIER = (
    "👋 Добро пожаловать, <b>{name}</b>!\n\n"
    "Вы успешно подключились как <b>Поставщик</b>.\n\n"
    "Вы будете получать уведомления о:\n"
    "• 📦 Подтверждённых счетах на закупку\n"
    "• 💳 Произведённых платежах"
)

ALREADY_LINKED = (
    "✅ Ваш аккаунт уже подключён.\n\n"
    "Уведомления о счетах и платежах будут приходить сюда."
)

NOT_LINKED = (
    "🔒 Ваш аккаунт не подключён.\n\n"
    "Отправьте /start для регистрации."
)

ASK_PHONE = (
    "📱 Введите ваш номер телефона для входа в систему:\n\n"
    "Пример: <code>+998901234567</code>"
)

PHONE_INVALID = (
    "❌ Неверный формат номера.\n\n"
    "Введите номер в формате: <code>+998901234567</code>"
)

PHONE_NOT_FOUND = (
    "❌ Номер телефона не найден в системе.\n\n"
    "Убедитесь, что номер совпадает с тем, который указан у менеджера.\n"
    "Попробуйте ещё раз или обратитесь к менеджеру."
)

# ─── Notifications: Customer ──────────────────────────────────────────────────

_LINE = "━━━━━━━━━━━━━━━━━━"

SALES_INVOICE_SUBMITTED = (
    "<b>{company}</b>\n"
    f"{_LINE}\n"
    "📅 Sana: {posting_date}\n"
    "🧾 Hujjat: #{name}\n"
    "👤 Mijoz: {customer}\n"
    "{title}\n"
    "{items}\n"
    "💰 Jami summa: {grand_total}\n"
    f"{_LINE}\n"
    "{balance_line}"
)

SALES_INVOICE_ITEM = (
    "📦 Tovar: {item_name}\n"
    "🔢 Miqdor: {qty}\n"
    "🏷️ Narx: {rate}"
)

CUSTOMER_PAYMENT = (
    "<b>{company}</b>\n"
    f"{_LINE}\n"
    "📅 Sana: {posting_date}\n"
    "🧾 Hujjat raqami: #{name}\n"
    "👤 Mijoz: {customer}\n\n"
    "{title}\n"
    "💰 {amount_label}: {amount}\n"
    f"{_LINE}\n"
    "{balance_line}"
)

# ─── Notifications: Supplier ─────────────────────────────────────────────────

PURCHASE_INVOICE_SUBMITTED = (
    "📦 <b>Счёт на закупку подтверждён</b>\n\n"
    "Номер: <code>{name}</code>\n"
    "Сумма: <b>{grand_total} {currency}</b>\n"
    "Дата: {posting_date}"
)

# ─── Notifications: Payment Entry (both parties) ─────────────────────────────

PAYMENT_RECEIVED = (
    "💳 <b>Получена оплата</b>\n\n"
    "Номер: <code>{name}</code>\n"
    "Сумма: <b>{paid_amount} {currency}</b>\n"
    "Дата: {posting_date}"
)

PAYMENT_SENT = (
    "💸 <b>Оплата произведена</b>\n\n"
    "Номер: <code>{name}</code>\n"
    "Сумма: <b>{paid_amount} {currency}</b>\n"
    "Дата: {posting_date}"
)

PAYMENT_CANCELLED = (
    "❌ <b>Платёж отменён</b>\n\n"
    "Номер: <code>{name}</code>\n"
    "Сумма: <b>{paid_amount} {currency}</b>"
)

# ─── Admin ────────────────────────────────────────────────────────────────────

ADMIN_WELCOME = (
    "👨‍💼 <b>Панель администратора</b>\n\n"
    "Выберите действие из меню ниже."
)

ADMIN_BOT_STATUS = (
    "ℹ️ <b>Статус бота</b>\n\n"
    "🤖 Username: @{username}\n"
    "🆔 Bot ID: <code>{bot_id}</code>\n"
    "👥 Клиентов подключено: <b>{customers}</b>\n"
    "🏭 Поставщиков подключено: <b>{suppliers}</b>"
)

ADMIN_NO_UNLINKED = "✅ Все контрагенты подключены к Telegram!"

ADMIN_UNLINKED_LIST = (
    "📋 <b>Без Telegram ({count})</b>\n\n"
    "{list}"
)

