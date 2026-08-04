"""Sales Order'ni ishlab chiqarish navbatiga ulash.

Jarayon:

    Operator SO yaratadi (docstatus 0, "Tasdiqqa jo'natish")
        │
        ▼  Kassir tasdiqlaydi (docstatus 1, "Tasdiqlash")
    har bir SO qatori uchun qoralama Production Entry (docstatus 0)
        │
        ▼  Ishlab chiqarish menedjeri tasdiqlaydi (submit)
    Stock Entry "Manufacture" → tayyor mahsulot omborga tushadi

Menedjer avvalgidek istalgan mahsulotni qo'lda ham ishlab chiqara oladi —
qo'lda yaratilgan PE'da `custom_manba` avtomatik "Qo'lda" bo'lib qoladi va bu
modul ularga umuman tegmaydi.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from armada.armada_custom_app.doctype.production_entry.production_entry import (
    get_bom_for_item,
    get_bom_items,
)

SOURCE_FIELD = "custom_manba"
SO_FIELD = "custom_sales_order"
SO_ITEM_FIELD = "custom_sales_order_item"
CUSTOMER_FIELD = "custom_mijoz"
DUE_FIELD = "custom_muddat"

SOURCE_MANUAL = "Qo'lda"
SOURCE_SALES_ORDER = "Zakazdan"


def create_production_entries(doc, method=None):
    """Kassir SO'ni tasdiqlagach har bir qator uchun qoralama Production Entry yaratadi.

    Sotuvni hech qachon to'smaydi: BOM topilmagan yoki kutilmagan xato yuz bergan
    qator o'tkazib yuboriladi va Sales Order'ga izoh sifatida yoziladi.
    """
    if not _fields_ready():
        return

    warehouse = _production_warehouse()
    created, skipped = [], []

    for idx, item in enumerate(doc.items):
        if _already_queued(item.name):
            continue

        bom_no, bom_required = _resolve_bom(item.item_code)
        if bom_required and not bom_no:
            skipped.append(item.item_code)
            continue

        save_point = f"armada_pe_{idx}"
        try:
            frappe.db.savepoint(save_point)
            created.append(_make_production_entry(doc, item, bom_no, warehouse).name)
        except Exception:
            frappe.db.rollback(save_point=save_point)
            skipped.append(item.item_code)
            frappe.log_error(
                title=f"Production Entry yaratilmadi — {doc.name} / {item.item_code}",
                message=frappe.get_traceback(),
            )

    _report(doc, created, skipped)


def release_production_entries(doc, method=None):
    """SO bekor qilinganda navbatda turgan qoralama PE'larni o'chiradi.

    Tasdiqlangan PE'lar tegilmaydi — mahsulot jismonan ishlab chiqarilgan va
    omborda turibdi. Ular bekor qilishni ham to'smasligi kerak: `custom_sales_order`
    Link maydoni bo'lgani uchun Frappe aks holda LinkExistsError beradi.

    Diqqat: ERPNext'ning `SalesOrder.on_cancel` metodi `ignore_linked_doctypes` ni
    o'zining ro'yxati bilan qayta yozadi. Shu sabab bu funksiya `before_cancel` emas,
    aynan `on_cancel` hook'ida — controller metodidan keyin — ishlashi shart.
    """
    if not _fields_ready():
        return

    doc.ignore_linked_doctypes = list(doc.get("ignore_linked_doctypes") or []) + [
        "Production Entry"
    ]

    rows = frappe.get_all(
        "Production Entry",
        filters={SO_FIELD: doc.name},
        fields=["name", "docstatus"],
    )

    for row in rows:
        if row.docstatus == 0:
            frappe.delete_doc(
                "Production Entry",
                row.name,
                ignore_permissions=True,
                delete_permanently=True,
            )

    submitted = [row.name for row in rows if row.docstatus == 1]
    if submitted:
        frappe.msgprint(
            _("Diqqat: {0} allaqachon ishlab chiqarilgan. Tayyor mahsulot omborda qoladi: {1}").format(
                doc.name, ", ".join(submitted)
            ),
            indicator="orange",
            title=_("Ishlab chiqarish bekor qilinmadi"),
        )


def _make_production_entry(so, item, bom_no, warehouse):
    qty = flt(item.stock_qty) or flt(item.qty)

    pe = frappe.new_doc("Production Entry")
    pe.company = so.company
    pe.item_to_manufacture = item.item_code
    pe.item_name = item.item_name
    pe.bom_no = bom_no
    pe.qty_to_manufacture = qty
    pe.target_warehouse = warehouse
    pe.remarks = _("Avtomatik: {0} zakazi").format(so.name)

    pe.set(SOURCE_FIELD, SOURCE_SALES_ORDER)
    pe.set(SO_FIELD, so.name)
    pe.set(SO_ITEM_FIELD, item.name)
    pe.set(CUSTOMER_FIELD, so.customer_name or so.customer)
    pe.set(DUE_FIELD, item.delivery_date or so.delivery_date)

    if bom_no:
        for row in get_bom_items(bom_no, qty, source_warehouse=warehouse):
            # validate_qty() nol miqdorli qatorda xato beradi — ularni tashlab ketamiz.
            if flt(row.get("required_qty")) <= 0:
                continue
            pe.append("items", row)

    pe.flags.ignore_permissions = True
    pe.insert()
    return pe


def _resolve_bom(item_code):
    """(bom_no, bom_majburiymi) qaytaradi.

    Item kartochkasida "BOM Not Required" yoqilgan bo'lsa BOM'siz ham PE yaratiladi
    (Production Entry.validate_bom shu belgini o'zi tekshiradi).
    """
    if cint(frappe.db.get_value("Item", item_code, "custom_no_bom_required")):
        return None, False

    return get_bom_for_item(item_code), True


def _already_queued(sales_order_item):
    """Bir SO qatoriga ikki marta PE yaratilmasin (amend / qayta submit holati)."""
    return bool(
        frappe.db.exists(
            "Production Entry",
            {SO_ITEM_FIELD: sales_order_item, "docstatus": ["<", 2]},
        )
    )


def _production_warehouse():
    """Production Entry doctype'idagi standart omborni ishlatamiz."""
    default = frappe.get_meta("Production Entry").get_field("target_warehouse").default
    if default and frappe.db.exists("Warehouse", default):
        return default

    return frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name")


def _fields_ready():
    """Migratsiya yurmagan bo'lsa sotuv jarayonini to'sib qo'ymaymiz."""
    meta = frappe.get_meta("Production Entry")
    return meta.has_field(SO_FIELD) and meta.has_field(SO_ITEM_FIELD)


def _report(so, created, skipped):
    if not created and not skipped:
        return

    lines = []
    if created:
        lines.append(_("Ishlab chiqarish navbatiga qo'shildi: {0}").format(", ".join(created)))
    if skipped:
        lines.append(
            _("BOM topilmagani uchun o'tkazib yuborildi: {0}").format(", ".join(sorted(set(skipped))))
        )

    so.add_comment("Comment", "<br>".join(lines))

    if skipped:
        frappe.msgprint(
            _("Bu mahsulotlarga BOM (retsept) yo'q, ishlab chiqarishga yuborilmadi: {0}").format(
                ", ".join(sorted(set(skipped)))
            ),
            indicator="orange",
            title=_("Ishlab chiqarish navbati"),
        )
