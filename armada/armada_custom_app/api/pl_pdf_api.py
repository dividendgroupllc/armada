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
    "5237 - Программа": "programma",
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


def _get_instagram_sold(col_keys, company):
    """ROW A1: Инстаграм mijozlari (customer 'Инстаграм%' bilan boshlanadi)
    bo'yicha submitted Sales Invoice Item qty summasi (oyma-oy).
    B2B = units_sold - instagram_sold (API da hisoblanadi)."""
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
          AND si.customer LIKE 'Инстаграм%%'
        GROUP BY YEAR(si.posting_date), MONTH(si.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_qty or 0)
    return [result.get(ck, 0.0) for ck in col_keys]


def _get_instagram_revenue(col_keys, company):
    """Инстаграм mijozlari bo'yicha submitted Sales Invoice Item
    base_net_amount summasi (oyma-oy) — P&L 'Выручка' qatori bilan bir manba
    (4110 ga net summa posting bo'ladi). B2B = revenue - instagram_revenue."""
    result = {ck: 0.0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(si.posting_date, '%%b')) AS mon,
            YEAR(si.posting_date)                      AS yr,
            SUM(sii.base_net_amount)                   AS total_amt
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.company   = %(company)s
          AND si.customer LIKE 'Инстаграм%%'
        GROUP BY YEAR(si.posting_date), MONTH(si.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_amt or 0)
    return [result.get(ck, 0.0) for ck in col_keys]


def _get_instagram_cogs(col_keys, company):
    """Инстаграм mijozlari bo'yicha COGS (5111) — GL Entry'dan (oyma-oy).
    5111 ga Sales Invoice va Delivery Note'lar posting qiladi; ikkalasida ham
    customer bor. Boshqa voucher'lar (Purchase Invoice — landed cost va h.k.)
    mijozsiz, ular B2B qoldiqqa tushadi (b2b = cogs - instagram_cogs)."""
    result = {ck: 0.0 for ck in col_keys}
    rows = frappe.db.sql("""
        SELECT
            LOWER(DATE_FORMAT(gl.posting_date, '%%b')) AS mon,
            YEAR(gl.posting_date)                      AS yr,
            SUM(gl.debit - gl.credit)                  AS total_amt
        FROM `tabGL Entry` gl
        LEFT JOIN `tabSales Invoice` si
               ON gl.voucher_type = 'Sales Invoice' AND si.name = gl.voucher_no
        LEFT JOIN `tabDelivery Note` dn
               ON gl.voucher_type = 'Delivery Note' AND dn.name = gl.voucher_no
        WHERE gl.account LIKE '5111%%'
          AND gl.is_cancelled = 0
          AND gl.company = %(company)s
          AND (si.customer LIKE 'Инстаграм%%' OR dn.customer LIKE 'Инстаграм%%')
        GROUP BY YEAR(gl.posting_date), MONTH(gl.posting_date)
    """, {"company": company}, as_dict=True)
    for r in rows:
        ck = f"{r.mon}_{r.yr}"
        if ck in result:
            result[ck] = float(r.total_amt or 0)
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


PROD_ACCOUNT    = "5204 - Зарплата Производства - AM"   # Зарплата Производства
PAYABLE_ACCOUNT = "2120 - Payroll Payable - AM"          # Hodimlar shu yerda (party)


def _get_production_workers(col_keys, company):
    """
    ROW D: Ishlab chiqarish ish haqi (5204) belgilangan DISTINCT hodimlar soni (oyma-oy).

    Journal Entry tuzilishi (idx tartibida):
      - Hodim qatori → account = 2120 (Payroll Payable), party_type = Employee, CREDIT
      - Darhol keyin uning xarajat qatori → 5204 / 5203 / 5202..., party'siz, DEBIT
      Aggregate holatda: barcha hodimlar oldin, oxirida yagona summa qatori.

    Mantiq (idx tartibi bo'yicha — summa bir xil bo'lsa ham ishonchli):
      - Hodimlarni ketma-ket buferga yig'amiz.
      - Xarajat (debit) qatoriga duch kelganda:
          * agar u 5204 bo'lsa → buferdagi hodimlarni ishlab chiqarishga qo'shamiz
          * keyin buferni tozalaymiz (5204 bo'lsin/bo'lmasin)
      Shunday qilib:
        paired   (hodim,5204,hodim,5202) → har hodim o'z xarajatiga bog'lanadi
        aggregate(hodimlar...,5204)      → barchasi 5204 ga
        aggregate(hodimlar...,5203)      → hech kim (5204 emas)
        aralash  (5 hodim,5204,3 hodim,5203) → faqat birinchi 5 tasi

    Oy bo'yicha: har JE o'z posting_date oyiga biriktiriladi.
    Hodim oyiga 1 marta sanaladi (DISTINCT per month).
    """
    from collections import defaultdict

    rows = frappe.db.sql("""
        SELECT
            je.name                                    AS je_name,
            LOWER(DATE_FORMAT(je.posting_date, '%%b')) AS mon,
            YEAR(je.posting_date)                      AS yr,
            jea.idx                                    AS idx,
            jea.account                                AS account,
            jea.party_type                             AS party_type,
            jea.party                                  AS party,
            jea.debit                                  AS debit,
            jea.credit                                 AS credit
        FROM `tabJournal Entry Account` jea
        JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus = 1
          AND je.company   = %(company)s
          AND je.name IN (
              SELECT parent
              FROM `tabJournal Entry Account`
              WHERE account = %(prod)s
          )
        ORDER BY je.name, jea.idx
    """, {"company": company, "prod": PROD_ACCOUNT}, as_dict=True)

    je_lines = defaultdict(list)
    je_month = {}
    for r in rows:
        je_lines[r.je_name].append(r)
        je_month[r.je_name] = f"{r.mon}_{r.yr}"

    month_emps = defaultdict(set)

    for je_name, lines in je_lines.items():
        ck    = je_month[je_name]
        lines = sorted(lines, key=lambda l: l.idx or 0)

        pending = []   # idx tartibida to'plangan hodimlar
        for l in lines:
            credit = float(l.credit or 0)
            debit  = float(l.debit or 0)

            is_emp = (l.account == PAYABLE_ACCOUNT
                      and l.party_type == "Employee"
                      and l.party and credit > 0)
            is_exp = (debit > 0 and l.account != PAYABLE_ACCOUNT)

            if is_emp:
                pending.append(l.party)
            elif is_exp:
                if l.account == PROD_ACCOUNT:
                    for p in pending:
                        month_emps[ck].add(p)
                pending = []   # flush

        # Xavfsizlik to'ri: oxirida hodim qoldi va JE dagi yagona
        # xarajat akkounti 5204 bo'lsa (teskari tartib ehtimoli) — qo'shamiz
        if pending:
            exp_accts = {l.account for l in lines
                         if float(l.debit or 0) > 0 and l.account != PAYABLE_ACCOUNT}
            if exp_accts == {PROD_ACCOUNT}:
                for p in pending:
                    month_emps[ck].add(p)

    return [len(month_emps.get(ck, set())) for ck in col_keys]


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
    data["instagram_sold"]     = _get_instagram_sold(col_keys, company)
    # Yaxlitlab ayiramiz — PDF da total = insta + b2b aynan mos tushishi uchun
    # (kasr qty bo'lsa, float ayirmada ko'rsatilgan yig'indi 1 ga farq qilishi mumkin)
    data["b2b_sold"]           = [round(u) - round(i) for u, i in
                                  zip(data["units_sold"], data["instagram_sold"])]
    # Выручка ham xuddi shunday Инстаграм/B2B ga ajratiladi.
    # Total sifatida report'dagi revenue olinadi — ko'rsatilganda
    # revenue = insta + b2b aynan mos tushishi uchun yaxlitlab ayiramiz.
    data["instagram_revenue"]  = _get_instagram_revenue(col_keys, company)
    _rev                       = data.get("revenue") or [0.0] * len(col_keys)
    data["b2b_revenue"]        = [round(r) - round(i) for r, i in
                                  zip(_rev, data["instagram_revenue"])]
    # Сырьевая себестоимость ham xuddi shunday ajratiladi
    data["instagram_cogs"]     = _get_instagram_cogs(col_keys, company)
    _cogs                      = data.get("cogs") or [0.0] * len(col_keys)
    data["b2b_cogs"]           = [round(c) - round(i) for c, i in
                                  zip(_cogs, data["instagram_cogs"])]
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
