"""Sales Order "Hudud" maydoniga barcha viloyatlarni qo'shish.

Eski "Viloyat" varianti ro'yxatda qoladi — u bilan saqlangan zakazlar
(2026-10 oyida ~69 ta) o'zgarmasin, bekor qilish/amend ishlayversin.
Yangi zakazlarda "Viloyat" formada ko'rinmaydi (public/js/sales_order_hudud.js)
va server tomonda ham bloklanadi (events/sales_order.validate_hudud).
"""

import frappe

HUDUD_FIELD = "custom_hudud"

VILOYATLAR = [
    "Toshkent viloyati",
    "Andijon",
    "Buxoro",
    "Farg'ona",
    "Jizzax",
    "Namangan",
    "Navoiy",
    "Qashqadaryo",
    "Qoraqalpog'iston",
    "Samarqand",
    "Sirdaryo",
    "Surxondaryo",
    "Xorazm",
]

# "Toshkent" — Toshkent shahri (eski qiymat, 600+ zakazda saqlangan).
# "Viloyat" — eskirgan, faqat eski zakazlar uchun.
OPTIONS = "\n".join(["", "Toshkent", *VILOYATLAR, "Viloyat"])


def execute():
    name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": HUDUD_FIELD})
    if not name:
        return
    frappe.db.set_value("Custom Field", name, "options", OPTIONS)
    frappe.clear_cache(doctype="Sales Order")
