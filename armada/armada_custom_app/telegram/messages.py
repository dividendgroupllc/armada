"""Botning barcha xabar shablonlari (o'zbek tilida)."""

# Xabarlarda ko'rinadigan brend nomi (ERPNext'dagi Company nomidan qat'i nazar)
BRAND_NAME = "HALOVAT MATRAS"

# ─── Onboarding ───────────────────────────────────────────────────────────────

WELCOME_CUSTOMER = (
    "👋 Xush kelibsiz, <b>{name}</b>!\n\n"
    "Siz <b>Mijoz</b> sifatida muvaffaqiyatli ulandingiz.\n\n"
    "Sizga quyidagilar haqida xabar keladi:\n"
    "• 📄 Rasmiylashtirilgan savdo hujjatlari\n"
    "• 💳 Qabul qilingan to'lovlar"
)

WELCOME_SUPPLIER = (
    "👋 Xush kelibsiz, <b>{name}</b>!\n\n"
    "Siz <b>Yetkazib beruvchi</b> sifatida muvaffaqiyatli ulandingiz.\n\n"
    "Sizga quyidagilar haqida xabar keladi:\n"
    "• 📦 Tasdiqlangan xarid hujjatlari\n"
    "• 💳 Amalga oshirilgan to'lovlar"
)

ALREADY_LINKED = (
    "✅ Hisobingiz allaqachon ulangan.\n\n"
    "Hujjatlar va to'lovlar haqidagi xabarlar shu yerga keladi."
)

NOT_LINKED = (
    "🔒 Hisobingiz ulanmagan.\n\n"
    "Ro'yxatdan o'tish uchun /start yuboring."
)

ASK_PHONE = (
    "📱 Tizimga kirish uchun telefon raqamingizni kiriting:\n\n"
    "Namuna: <code>+998901234567</code>"
)

PHONE_INVALID = (
    "❌ Raqam formati noto'g'ri.\n\n"
    "Raqamni quyidagi formatda kiriting: <code>+998901234567</code>"
)

PHONE_NOT_FOUND = (
    "❌ Telefon raqam tizimda topilmadi.\n\n"
    "Raqam menejerda ko'rsatilgan raqam bilan bir xil ekanligini tekshiring.\n"
    "Qaytadan urinib ko'ring yoki menejerga murojaat qiling."
)

# ─── Notifications: Customer ──────────────────────────────────────────────────

_LINE = "━━━━━━━━━━━━━━━━━━"

SALES_INVOICE_SUBMITTED = (
    f"<b>{BRAND_NAME}</b>\n"
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

SALES_INVOICE_COMMENT = "📝 Izohi: {comment}"

CUSTOMER_PAYMENT = (
    f"<b>{BRAND_NAME}</b>\n"
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
    "📦 <b>Xarid hujjati tasdiqlandi</b>\n\n"
    "Raqam: <code>{name}</code>\n"
    "Summa: <b>{grand_total} {currency}</b>\n"
    "Sana: {posting_date}"
)

# ─── Notifications: Payment Entry (both parties) ─────────────────────────────

PAYMENT_RECEIVED = (
    "💳 <b>To'lov qabul qilindi</b>\n\n"
    "Raqam: <code>{name}</code>\n"
    "Summa: <b>{paid_amount} {currency}</b>\n"
    "Sana: {posting_date}"
)

PAYMENT_SENT = (
    "💸 <b>To'lov amalga oshirildi</b>\n\n"
    "Raqam: <code>{name}</code>\n"
    "Summa: <b>{paid_amount} {currency}</b>\n"
    "Sana: {posting_date}"
)

PAYMENT_CANCELLED = (
    "❌ <b>To'lov bekor qilindi</b>\n\n"
    "Raqam: <code>{name}</code>\n"
    "Summa: <b>{paid_amount} {currency}</b>"
)

# ─── Admin ────────────────────────────────────────────────────────────────────

ADMIN_WELCOME = (
    "👨‍💼 <b>Administrator paneli</b>\n\n"
    "Quyidagi menyudan amalni tanlang."
)

ADMIN_BOT_STATUS = (
    "ℹ️ <b>Bot holati</b>\n\n"
    "🤖 Username: @{username}\n"
    "🆔 Bot ID: <code>{bot_id}</code>\n"
    "👥 Ulangan mijozlar: <b>{customers}</b>\n"
    "🏭 Ulangan yetkazib beruvchilar: <b>{suppliers}</b>"
)

ADMIN_NO_UNLINKED = "✅ Barcha kontragentlar Telegram'ga ulangan!"

ADMIN_UNLINKED_LIST = (
    "📋 <b>Telegram'siz ({count})</b>\n\n"
    "{list}"
)
