"""
armada_custom_app/api/balance_pdf_api.py
Balance Sheet PDF API — fetches data from ERPNext, generates PDF

Same pattern as pl_pdf_api.py:
  1. ERPNext balance_sheet.execute() → data (0 extra queries)
  2. P&L execute() → revenue/COGS for ratios (1 extra query)
  3. balance_pdf.generate() → PDF file (0 DB queries)
"""
import frappe
import json
import os


# ─── ACCOUNT KEY MAP ─────────────────────────────────────────────────────────
# ERPNext account_name → balance_pdf data key
# NOTE: " - AM" (company abbreviation suffix) is stripped before lookup
#
# Adjust these if your Chart of Accounts differs.
# Run: bench execute armada.armada_custom_app.api.balance_pdf_api.debug_accounts
# to see all accounts returned by balance_sheet report.

ACCOUNT_KEY_MAP = {
    # ── Assets (individual accounts) ──
    # Основные средства (Fixed assets) — bir qatorга yig'iladi
    "1740 - Office Equipments":               "oborudovanie",
    "1750 - Plants and Machineries":          "oborudovanie",
    # Запасы (Inventory)
    "1410 - Склад Сырьё":                    "syryo",
    "1420 - Склад Производство":              "polufabrikat",
    "1430 - Склад ГП":                        "gotoviy_produkt",
    # Денежные средства (Cash)
    "1110 - Наличные":                        "nalichnye",
    "1111 - Клик":                            "klik",
    "1112 - Перечисление":                    "perechislenie",
    # Разница в перемещении — hozircha ERPNext'da yo'q
    # "XXXX - Разница в перемещении":            "raznitsa_peremesh",

    # NOTE: Kontragent qatorlari (Задолженность клиентов / Авансы клиентов /
    # Задолженность поставщикам / Авансы поставщикам / Задолженность
    # сотрудников(-ам)) bu mapda YO'Q — ular hisob qoldig'idan emas,
    # Kontragent Otchet kabi har kontragent bo'yicha netto hisoblanadi.
    # Qarang: _party_balances()

    # ── Liabilities & Equity (individual accounts) ──
    # Капитал
    "3300 - Уставный капитал":                "ustavniy_kapital",
    "3400 - Retained Earnings":               "pribyl_proshlyh",
    "3200 - Дивидент":                        "dividendy",
    # Hozircha ERPNext'da yo'q:
    # "XXXX - Инвестиция":                       "investiciya",
    # Долгосрочные обязательства — hozircha ERPNext'da yo'q
    # "XXXX - Кредит банка (долгосрочный)":      "kredit_bank_dolg",
    # "XXXX - Займы (долгосрочные)":             "zaymy_dolg",
    # "XXXX - Лизинг":                           "lizing",
    # Краткосрочные обязательства — hozircha ERPNext'da yo'q
    # "XXXX - Кредит банка (краткосрочный)":     "kredit_bank_kratk",
    # "XXXX - Займы (краткосрочные)":            "zaymy_kratk",
    # Hozircha ERPNext'da yo'q:
    # "XXXX - Tax Payable":                      "zadolzh_nalog",
    # "XXXX - Owner Salary":                     "zarplata_sobstvennika",
    # "XXXX - Other Payables":                   "prochie_obyaz",

    # ── ERPNext calculated totals ──
    # Прибыль текущего периода (Provisional P/L from ERPNext)
    "'Provisional Profit / Loss (Credit)'":   "pribyl_tekushih",
    # NOTE: 'Total Asset (Debit)' / 'Total (Credit)' ataylab map qilinmagan:
    # ular hisob-based brutto jami bo'lib, kontragent-netto qatorlar bilan
    # mos kelmaydi. Итого endi PDF'da ko'rinadigan bo'limlar yig'indisidan
    # hisoblanadi (balance_pdf._derive fallback).
}


# Kontragent Otchet bilan bir xil qoidada taqsimlash:
# har kontragent bo'yicha netto debet → aktiv qator, netto kredit → passiv qator
PARTY_DEBIT_KEY = {
    "Customer": "zadolzh_klientov",      # Задолженность клиентов
    "Supplier": "avansy_postavshikam",   # Авансы поставщикам
    "Employee": "zadolzh_sotrudnikov",   # Задолженность сотрудников (aktiv)
}
PARTY_CREDIT_KEY = {
    "Customer": "avansy_klientov",       # Авансы клиентов
    "Supplier": "zadolzh_postavshik",    # Задолженность поставщикам
    "Employee": "zadolzh_sotrudnikam",   # Задолженность сотрудникам (passiv)
}

_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,  "may": 5,  "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _column_end_dates(col_keys, period_end_date):
    """col_key ('jan_2026') → shu ustunning oxirgi sanasi (oy oxiri,
    period_end bilan cheklangan)."""
    import calendar
    from frappe.utils import getdate

    period_end = getdate(period_end_date)
    ends = []
    for ck in col_keys:
        parts = ck.split("_")
        mon = _MONTH_NUM.get(parts[0].lower())
        if mon and len(parts) > 1 and parts[1].isdigit():
            year = int(parts[1])
            from datetime import date
            month_end = date(year, mon, calendar.monthrange(year, mon)[1])
            ends.append(min(month_end, period_end))
        else:
            ends.append(period_end)
    return ends


def _party_balances(company, col_keys, period_end_date):
    """Kontragent Otchet uslubida: har (party_type, party) bo'yicha barcha
    hisoblardagi netto qoldiq (debit − credit) har ustun oxiriga hisoblanadi,
    so'ng musbat → aktiv qator, manfiy → passiv qatorga yig'iladi.

    Natija Kontragent Otchet'ning «Сўнгги Дебет» / «Сўнгги Кредит»
    ЖАМИ qiymatlari bilan aynan mos keladi."""
    from collections import defaultdict
    from frappe.utils import flt

    ends = _column_end_dates(col_keys, period_end_date)
    out = {
        key: [0.0] * len(ends)
        for key in list(PARTY_DEBIT_KEY.values()) + list(PARTY_CREDIT_KEY.values())
    }
    if not ends:
        return out

    rows = frappe.db.sql(
        """
        SELECT
            party_type,
            party,
            YEAR(posting_date)  AS yr,
            MONTH(posting_date) AS mo,
            SUM(debit - credit) AS net
        FROM `tabGL Entry`
        WHERE
            is_cancelled = 0
            AND company = %(company)s
            AND party_type IN ('Customer', 'Supplier', 'Employee')
            AND party IS NOT NULL AND party != ''
            AND posting_date <= %(last_date)s
        GROUP BY party_type, party, YEAR(posting_date), MONTH(posting_date)
        """,
        {"company": company, "last_date": ends[-1]},
        as_dict=True,
    )

    per_party = defaultdict(lambda: defaultdict(float))
    for r in rows:
        per_party[(r.party_type, r.party)][(int(r.yr), int(r.mo))] += flt(r.net)

    for (party_type, _party), months in per_party.items():
        for i, end in enumerate(ends):
            bal = sum(
                v for (y, m), v in months.items()
                if (y, m) <= (end.year, end.month)
            )
            if bal > 0:
                out[PARTY_DEBIT_KEY[party_type]][i] += bal
            elif bal < 0:
                out[PARTY_CREDIT_KEY[party_type]][i] += -bal

    return out

@frappe.whitelist()
def generate_balance_pdf(filters):
    """
    Main API endpoint. Called from JS button on Balance Sheet page.
    Returns { file_url, file_name }
    """
    if isinstance(filters, str):
        filters = json.loads(filters)

    normalized = _normalize_filters(filters)

    # ── 1. Balance Sheet data ──
    bs_execute = frappe.get_attr(
        "erpnext.accounts.report.balance_sheet"
        ".balance_sheet.execute"
    )
    columns, rows, *_ = bs_execute(frappe._dict(normalized))

    # Extract dynamic column keys (monthly fieldnames)
    skip_fields = {
        "account", "currency", "total", "account_name",
        "indent", "parent_account", "is_group", "has_value",
        "account_type", "opening_balance", "include_in_gross",
        "year_start_date", "year_end_date",
    }
    col_keys = [
        c["fieldname"] for c in columns
        if c["fieldname"] not in skip_fields
        and c.get("fieldtype") == "Currency"
        and c["fieldname"] != "total"
    ]
    n_cols = len(col_keys)

    # Parse BS rows → data dict (cumulative — for balance accounts)
    data = _extract_rows(rows, col_keys, ACCOUNT_KEY_MAP)

    # ── 1b. Flow rows (monthly, not cumulative) ──
    # pribyl_tekushih va dividendy — analiz uchun oylik harakatni ko'rsatamiz,
    # shunda: prev_pribyl_proshlyh + pribyl_tekushih + dividendy = next_pribyl_proshlyh
    monthly_filters = dict(normalized)
    monthly_filters["accumulated_values"] = 0
    _, monthly_rows, *_ = bs_execute(frappe._dict(monthly_filters))
    monthly_data = _extract_rows(monthly_rows, col_keys, ACCOUNT_KEY_MAP)
    for flow_key in ("pribyl_tekushih", "dividendy"):
        if flow_key in monthly_data:
            data[flow_key] = monthly_data[flow_key]

    # ── 1c. Kontragent qatorlari — Kontragent Otchet bilan bir xil netto ──
    data.update(_party_balances(
        normalized.get("company"),
        col_keys,
        normalized.get("period_end_date"),
    ))

    # ── 2. Generate PDF ──
    from armada.armada_custom_app.pdf_engine.balance_pdf import generate

    company  = normalized.get("company", "report").replace(" ", "_")
    start    = normalized.get("period_start_date", "")[:7]
    end      = normalized.get("period_end_date", "")[:7]
    filename = f"BS_{company}_{start}_to_{end}.pdf"

    output_path = generate(data, filename, col_keys=col_keys)

    # ── 4. Create Frappe File doc ──
    site_path = frappe.get_site_path("private", "files", filename)
    if not os.path.exists(site_path):
        import shutil
        shutil.copy(output_path, site_path)

    # Remove old duplicate
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

    return {
        "file_url":  file_doc.file_url,
        "file_name": filename,
    }


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _extract_rows(rows, col_keys, key_map):
    """
    Parse report rows into { data_key: [val1, val2, ...] } dict.
    Strips ' - AM' (company abbreviation) from account names before lookup.
    """
    data = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        acct_name = str(row.get("account_name") or row.get("account") or "")
        # Strip company abbreviation suffix
        if " - AM" in acct_name:
            acct_name = acct_name.replace(" - AM", "").strip()

        key = key_map.get(acct_name)
        if not key:
            continue

        values = [float(row.get(ck) or 0) for ck in col_keys]

        # Balance sheet: assets are positive debit, liabilities positive credit
        # ERPNext returns: Assets as positive, Liabilities as positive
        # For balance report display: liabilities shown as positive too
        # Dividends may be negative — keep as-is
        # Bir kalitga bir nechta hisob mos kelsa (1740+1750 → oborudovanie)
        # qiymatlar yig'iladi.
        if key in data:
            data[key] = [a + b for a, b in zip(data[key], values)]
        else:
            data[key] = values

    return data


def _normalize_filters(f):
    """Normalize filter dict for ERPNext report execute()."""
    result = {
        "company":            f.get("company"),
        "filter_based_on":    f.get("filter_based_on", "Date Range"),
        "period_start_date":  f.get("period_start_date"),
        "period_end_date":    f.get("period_end_date"),
        "from_fiscal_year":   f.get("from_fiscal_year"),
        "to_fiscal_year":     f.get("to_fiscal_year"),
        "periodicity":        f.get("periodicity", "Monthly"),
        "accumulated_values": int(f.get("accumulated_values", 1)),
        "include_default_book_entries": int(
            f.get("include_default_book_entries", 1)),
    }

    # "Fiscal Year" rejimida ERPNext period_start_date/period_end_date talab qiladi
    if result["filter_based_on"] != "Date Range" and not result["period_start_date"]:
        from_fy = result.get("from_fiscal_year")
        to_fy = result.get("to_fiscal_year")
        if from_fy and to_fy:
            fy_start = frappe.db.get_value(
                "Fiscal Year", from_fy, "year_start_date"
            )
            fy_end = frappe.db.get_value(
                "Fiscal Year", to_fy, "year_end_date"
            )
            if fy_start and fy_end:
                result["period_start_date"] = str(fy_start)
                result["period_end_date"] = str(fy_end)

    return result


# ─── DEBUG HELPER ────────────────────────────────────────────────────────────

def debug_accounts(company="ARMADA MATRAS",
                   from_date="2025-04-01", to_date="2025-12-31"):
    """
    Run from bench console to see all BS accounts and find correct mappings:
        bench execute armada.armada_custom_app.api.balance_pdf_api.debug_accounts
    """
    execute = frappe.get_attr(
        "erpnext.accounts.report.balance_sheet.balance_sheet.execute"
    )
    filters = frappe._dict({
        "company": company,
        "filter_based_on": "Date Range",
        "period_start_date": from_date,
        "period_end_date": to_date,
        "periodicity": "Monthly",
        "accumulated_values": 1,
        "include_default_book_entries": 1,
    })

    columns, rows, *_ = execute(filters)

    print("\n=== BALANCE SHEET ACCOUNTS ===")
    print(f"{'account_name':<50} {'indent':>6} {'is_group':>8}")
    print("-" * 70)
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("account_name") or row.get("account") or "")
        if " - AM" in name:
            name = name.replace(" - AM", "").strip()
        indent = row.get("indent", 0)
        is_grp = row.get("is_group", False)
        mapped = "✓" if name in ACCOUNT_KEY_MAP else ""
        print(f"{name:<50} {indent:>6} {str(is_grp):>8} {mapped}")

    print("\n=== UNMAPPED LEAF ACCOUNTS ===")
    for row in rows:
        if not isinstance(row, dict) or row.get("is_group"):
            continue
        name = str(row.get("account_name") or row.get("account") or "")
        if " - AM" in name:
            name = name.replace(" - AM", "").strip()
        if name not in ACCOUNT_KEY_MAP:
            print(f"  MISSING: {name}")
