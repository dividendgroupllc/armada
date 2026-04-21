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
    # Основные средства (Fixed assets) — hozircha ERPNext'da yo'q, kerak bo'lsa qo'shing
    # "XXXX - Оборудование":                    "oborudovanie",
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
    # Дебиторская задолженность (Receivables)
    "1310 - Debtors":                         "zadolzh_klientov",
    # Quyidagi accountlar hozircha ERPNext'da yo'q, kerak bo'lsa qo'shing:
    # "XXXX - Advance to Suppliers":            "avansy_postavshikam",
    # "XXXX - Employee Receivable":             "zadolzh_sotrudnikov",
    # "XXXX - Other Debtors":                   "dolg_debitorov",
    # Прочие активы — hozircha ERPNext'da yo'q
    # "XXXX - Расходы будущих периодов":         "rashody_budushih",
    # "XXXX - Прочее":                           "prochee_aktiv",

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
    # Кредиторская задолженность
    "2110 - Creditors":                       "zadolzh_postavshik",
    "2120 - Payroll Payable":                 "zadolzh_sotrudnikam",
    # Hozircha ERPNext'da yo'q:
    # "XXXX - Tax Payable":                      "zadolzh_nalog",
    # "XXXX - Advance from Customers":           "avansy_klientov",
    # "XXXX - Owner Salary":                     "zarplata_sobstvennika",
    # "XXXX - Other Payables":                   "prochie_obyaz",

    # ── ERPNext calculated totals ──
    # Прибыль текущего периода (Provisional P/L from ERPNext)
    "'Provisional Profit / Loss (Credit)'":   "pribyl_tekushih",
    # Итого строки — ERPNext'dan to'g'ridan-to'g'ri
    "'Total Asset (Debit)'":                  "_erp_total_asset",
    "'Total (Credit)'":                       "_erp_total_credit",
}

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
