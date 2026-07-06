import frappe
from frappe.utils import flt


def set_valuation_rate(doc, method=None):
    """BOM mahsulotining tan narxi — eng oxirgi Manufacture Stock Entry'dagi
    tayyor mahsulot kirim narxi (o'sha paytda ishlatilgan siriyolarning
    valuation qiymatidan hisoblangan)."""
    if not doc.item:
        return

    try:
        doc.custom_basic_rate = get_last_manufacture_rate(doc.item)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "BOM valuation rate error")


def get_last_manufacture_rate(item_code):
    last_entry = frappe.db.sql(
        """
        SELECT sed.parent
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1
          AND se.purpose = 'Manufacture'
          AND sed.is_finished_item = 1
          AND sed.item_code = %s
        ORDER BY se.posting_date DESC, se.posting_time DESC, se.creation DESC
        LIMIT 1
        """,
        (item_code,),
    )

    if last_entry:
        rate = frappe.db.sql(
            """
            SELECT SUM(sed.basic_amount) / NULLIF(SUM(sed.transfer_qty), 0)
            FROM `tabStock Entry Detail` sed
            WHERE sed.parent = %s
              AND sed.is_finished_item = 1
              AND sed.item_code = %s
            """,
            (last_entry[0][0], item_code),
        )
        if rate and rate[0][0]:
            return flt(rate[0][0])

    # Hali ishlab chiqarilmagan mahsulot — ombordagi joriy o'rtacha valuation.
    bin_rate = frappe.db.sql(
        """
        SELECT SUM(stock_value) / NULLIF(SUM(actual_qty), 0)
        FROM `tabBin`
        WHERE item_code = %s
        """,
        (item_code,),
    )
    return flt(bin_rate[0][0]) if bin_rate and bin_rate[0][0] else 0
