"""
armada_custom_app/api/pl_pdf_api.py  —  FINAL

O'zgarishlar:
  - Яндекс инстаграм (5236) → "yandex_inst"
  - Кредит / Алименты ACCOUNT_KEY_MAP da yo'q (CoA dan o'chirilgan)
  - 4 yangi metrik funksiya: units_sold, units_produced,
    production_cost, production_workers
  - Company nomi filterdan olinadi (default: ARMADA MATRAS)
"""
import frappe
import json
import os

ACCOUNT_KEY_MAP = {
    "4110 - Sales": "revenue",
    "5111 - Cost of Goods Sold": "cogs",
    "5119 - Stock Adjustment": "loss_adj",
    # Manufacturing
    "5201 - Аренда цех": "arenda_cex",
    "5204 - Зарплата Производства": "zarplata_pr",
    "5208 - Коммунальный платёж": "komunal",
    "5215 - Продукт": "produkt",
    "5216 - Производство": "proizvodstvo",
    # Admin
    "5202 - Бонус сотрудникам": "bonus",
    "5203 - Зарплата Админстрация": "zarplata_adm",
    "5205 - ИНПС": "inps",
    "5206 - Комиссия банка": "komis_bank",
    "5207 - Комиссия клик": "komis_klik",
    "5209 - Мобильный банк": "mobil_bank",
    "5210 - НДС": "nds",
    "5211 - Обед, Чойхона": "obed",
    "5213 - Подоходный налог": "podoh_nalog",
    "5214 - Праздник": "prazdnik",
    "5217 - Прочие": "prochie",
    "5219 - Скидка": "skidka",
    "5220 - СП": "sp",
    "5221 - Стоянка": "stoyanka",
    "5222 - Транспорт": "transport",
    "5223 - Утилизация отходов": "utilizaciya",
    "5224 - Финансовые услуги": "fin_uslugi",
    "5225 - Офис": "ofis",
    "5227 - Яндекс": "yandex",
    "5236 - Яндекс инстаграм": "yandex_inst",   # CHANGE 3: yangi account
    "5233 - Услуги": "uslugi",
    "5234 - Канцтовар": "kantc",
    # Commercial
    "5218 - Реклама и маркетинг": "reklama",
    "5226 - Хайрия эхсон": "khairiya",
    # Tax
    "5232 - Налог на прибыль": "nalog_prib",
    # CHANGE 2: Кредит va Алименты o'chirilgan (CoA dan)
}


# ── CHANGE 4: 4 yangi metrik funksiyalar ────────────────────────────────────────

def _get_units_sold(col_keys, company):
    """ROW A: Барча submitted Sales Invoice Item qty summasi (oyma-oy)."""
    result = {ck: 0.0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(si.posting_date, '%%b')) AS mon,
            YEAR(si.posting_date)                      AS yr,
            SUM(sii.qty)                               AS total_qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.company   = %(company)s
        GROUP BY YEAR(si.posting_date), MONTH(si.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_qty or 0)
    return [result.get(ck, 0.0) for ck in col_keys]


def _get_units_produced(col_keys, company):
    """ROW B: Production Entry qty_to_manufacture summasi (oyma-oy)."""
    result = {ck: 0.0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(posting_date, '%%b')) AS mon,
            YEAR(posting_date)                      AS yr,
            SUM(qty_to_manufacture)                 AS total_qty
        FROM `tabProduction Entry`
        WHERE docstatus = 1
          AND company   = %(company)s
        GROUP BY YEAR(posting_date), MONTH(posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_qty or 0)
    return [result.get(ck, 0.0) for ck in col_keys]


def _get_production_cost(col_keys, company):
    """ROW C: BOM.total_cost * Production Entry.qty_to_manufacture (oyma-oy)."""
    result = {ck: 0.0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(pe.posting_date, '%%b')) AS mon,
            YEAR(pe.posting_date)                      AS yr,
            SUM(b.total_cost * pe.qty_to_manufacture)  AS total_cost
        FROM `tabProduction Entry` pe
        JOIN `tabBOM` b ON b.name = pe.bom_no
        WHERE pe.docstatus = 1
          AND pe.company   = %(company)s
          AND b.docstatus  = 1
        GROUP BY YEAR(pe.posting_date), MONTH(pe.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_cost or 0)
    return [result.get(ck, 0.0) for ck in col_keys]


def _get_production_workers(col_keys, company):
    """
    ROW D: 5204 - Зарплата Производства - AM ga bog'liq
    DISTINCT employee (party) soni (oyma-oy).
    """
    result = {ck: 0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(je.posting_date, '%%b')) AS mon,
            YEAR(je.posting_date)                      AS yr,
            COUNT(DISTINCT jea.party)                  AS worker_count
        FROM `tabJournal Entry Account` jea
        JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus   = 1
          AND je.company     = %(company)s
          AND jea.account    = '5204 - Зарплата Производства - AM'
          AND jea.party_type = 'Employee'
          AND jea.party IS NOT NULL
          AND jea.party != ''
        GROUP BY YEAR(je.posting_date), MONTH(je.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = int(r.worker_count or 0)
    return [result.get(ck, 0) for ck in col_keys]


# ────────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def generate_pl_pdf(filters):
    if isinstance(filters, str):
        filters = json.loads(filters)

    normalized = _normalize_filters(filters)

    execute = frappe.get_attr(
        "erpnext.accounts.report.profit_and_loss_statement"
        ".profit_and_loss_statement.execute"
    )
    columns, rows, *_ = execute(frappe._dict(normalized))

    skip = {"account", "currency", "total", "account_name",
            "indent", "parent_account", "is_group", "has_value",
            "account_type", "opening_balance", "include_in_gross",
            "year_start_date", "year_end_date"}

    col_keys = [
        c["fieldname"] for c in columns
        if c["fieldname"] not in skip
           and c.get("fieldtype") == "Currency"
           and c["fieldname"] != "total"
    ]

    # Parse rows → data dict
    data = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        acct_name = str(row.get("account_name") or row.get("account") or "")
        if " - AM" in acct_name:
            acct_name = acct_name.replace(" - AM", "").strip()

        key = ACCOUNT_KEY_MAP.get(acct_name)
        if not key:
            code = acct_name.split(" - ")[0].strip()
            for map_name, map_key in ACCOUNT_KEY_MAP.items():
                if map_name.split(" - ")[0].strip() == code:
                    key = map_key
                    break

        if key:
            data[key] = [float(row.get(ck) or 0) for ck in col_keys]

    # ── CHANGE 4: 4 yangi metrik qator ──
    # Company nomi filterdan olinadi (masalan "ARMADA MATRAS")
    company = normalized.get("company") or "ARMADA MATRAS"

    data["units_sold"]         = _get_units_sold(col_keys, company)
    data["units_produced"]     = _get_units_produced(col_keys, company)
    data["production_cost"]    = _get_production_cost(col_keys, company)
    data["production_workers"] = _get_production_workers(col_keys, company)

    # PDF yaratish
    from armada.armada_custom_app.pdf_engine.pl_pdf import generate

    start    = (normalized.get("period_start_date") or "")[:7]
    end      = (normalized.get("period_end_date") or "")[:7]
    safe_co  = company.replace(" ", "_")
    filename = f"PL_{safe_co}_{start}_to_{end}.pdf"

    output_path = generate(data, filename, col_keys=col_keys)

    site_path = frappe.get_site_path("private", "files", filename)
    if not os.path.exists(site_path):
        import shutil
        shutil.copy(output_path, site_path)

    existing = frappe.db.exists("File", {"file_name": filename})
    if existing:
        frappe.delete_doc("File", existing, ignore_permissions=True)

    file_doc = frappe.get_doc({
        "doctype":    "File",
        "file_name":  filename,
        "file_url":   f"/private/files/{filename}",
        "is_private": 1,
        "folder":     "Home/Attachments",
    })
    file_doc.flags.ignore_permissions = True
    file_doc.insert()

    return {"file_url": file_doc.file_url, "file_name": filename}


def _normalize_filters(f):
    return {
        "company":                      f.get("company"),
        "filter_based_on":              f.get("filter_based_on", "Date Range"),
        "period_start_date":            f.get("period_start_date"),
        "period_end_date":              f.get("period_end_date"),
        "from_fiscal_year":             f.get("from_fiscal_year"),
        "to_fiscal_year":               f.get("to_fiscal_year"),
        "periodicity":                  f.get("periodicity", "Monthly"),
        "accumulated_values":           int(f.get("accumulated_values", 0)),
        "include_default_book_entries": int(f.get("include_default_book_entries", 1)),
    }
