# Copyright (c) 2026, abdulloh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    summary_html = get_summary_html(data)
    return columns, data, summary_html


def get_columns():
    return [
        {
            "fieldname": "posting_date",
            "label": _("Сана"),
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "voucher_type",
            "label": _("Тип"),
            "fieldtype": "Data",
            "width": 0,
            "hidden": 1
        },
        {
            "fieldname": "voucher_no",
            "label": _("Документ"),
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 180
        },
        {
            "fieldname": "description",
            "label": _("Контрагент / Изоҳ"),
            "fieldtype": "Data",
            "width": 280
        },
        {
            "fieldname": "kirim",
            "label": _("Кирим"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "chiqim",
            "label": _("Чиқим"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "balance",
            "label": _("Қолдиқ"),
            "fieldtype": "Currency",
            "width": 130
        },
    ]


def get_data(filters):
    cash_accounts = get_cash_accounts(filters)
    if not cash_accounts:
        return []

    opening_balance = get_opening_balance(cash_accounts, filters)
    transactions = get_transactions(cash_accounts, filters)

    # Payment Entry va Journal Entry dan party info'ni batch-fetch
    pe_vouchers = [r.voucher_no for r in transactions if r.voucher_type == "Payment Entry"]
    je_vouchers = [r.voucher_no for r in transactions if r.voucher_type == "Journal Entry"]

    pe_info = get_payment_entry_info_batch(pe_vouchers)
    je_info = get_journal_entry_info_batch(je_vouchers)

    data = []

    # Opening balance qatori
    data.append({
        "posting_date": None,
        "voucher_type": None,
        "voucher_no": None,
        "description": _("Нач. остаток"),
        "kirim": 0,
        "chiqim": 0,
        "balance": opening_balance,
        "is_opening": 1,
    })

    # Transactions
    balance = opening_balance
    total_kirim = 0
    total_chiqim = 0

    for row in transactions:
        kirim = flt(row.debit_in_account_currency)
        chiqim = flt(row.credit_in_account_currency)
        balance += kirim - chiqim
        total_kirim += kirim
        total_chiqim += chiqim

        # Party info va category aniqlash
        info = resolve_transaction_info(row, pe_info, je_info, cash_accounts)

        data.append({
            "posting_date": row.posting_date,
            "voucher_type": row.voucher_type,
            "voucher_no": row.voucher_no,
            "description": info["description"],
            "kirim": kirim,
            "chiqim": chiqim,
            "balance": balance,
            "category": info["category"],
        })

    # ИТОГО qatori
    data.append({
        "posting_date": None,
        "voucher_type": None,
        "voucher_no": None,
        "description": _("ИТОГО"),
        "kirim": total_kirim,
        "chiqim": total_chiqim,
        "balance": balance,
        "is_total": 1,
    })

    return data


def get_cash_accounts(filters):
    """Mode of Payment dan cash account'larni olish"""
    conditions = {}
    if filters.get("mode_of_payment"):
        conditions["parent"] = filters["mode_of_payment"]

    accounts = frappe.get_all(
        "Mode of Payment Account",
        filters=conditions,
        fields=["default_account"],
        pluck="default_account"
    )

    return list(set(a for a in accounts if a))


def get_opening_balance(cash_accounts, filters):
    """from_date gacha bo'lgan balans"""
    placeholders = ", ".join(["%s"] * len(cash_accounts))

    result = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency) - SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE account IN ({placeholders})
          AND posting_date < %s
          AND is_cancelled = 0
    """.format(placeholders=placeholders),
        tuple(cash_accounts) + (filters["from_date"],)
    )

    return flt(result[0][0]) if result else 0


def get_transactions(cash_accounts, filters):
    """Davr ichidagi barcha transaction'lar"""
    placeholders = ", ".join(["%s"] * len(cash_accounts))

    return frappe.db.sql("""
        SELECT
            posting_date, voucher_type, voucher_no,
            party_type, party, against,
            debit_in_account_currency, credit_in_account_currency,
            account
        FROM `tabGL Entry`
        WHERE account IN ({placeholders})
          AND posting_date BETWEEN %s AND %s
          AND is_cancelled = 0
        ORDER BY posting_date, creation
    """.format(placeholders=placeholders),
        tuple(cash_accounts) + (filters["from_date"], filters["to_date"]),
        as_dict=True
    )


def get_payment_entry_info_batch(voucher_nos):
    """Barcha Payment Entry'lardan party info olish"""
    if not voucher_nos:
        return {}

    entries = frappe.db.sql("""
        SELECT name, party_type, party, payment_type
        FROM `tabPayment Entry`
        WHERE name IN %s
    """, (voucher_nos,), as_dict=True)

    result = {}
    for e in entries:
        result[e.name] = e
    return result


def get_journal_entry_info_batch(voucher_nos):
    """Barcha Journal Entry'lardan against account info olish"""
    if not voucher_nos:
        return {}

    # JE Account'lardan party yoki account info olish
    entries = frappe.db.sql("""
        SELECT jea.parent, jea.account, jea.party_type, jea.party,
               acc.root_type, acc.account_type, acc.account_name
        FROM `tabJournal Entry Account` jea
        LEFT JOIN `tabAccount` acc ON acc.name = jea.account
        WHERE jea.parent IN %s
    """, (voucher_nos,), as_dict=True)

    result = {}
    for e in entries:
        if e.parent not in result:
            result[e.parent] = []
        result[e.parent].append(e)
    return result


def resolve_transaction_info(row, pe_info, je_info, cash_accounts):
    """Transaction uchun description va category aniqlash"""

    # 1. GL Entry'da party bor bo'lsa — to'g'ridan-to'g'ri ishlatamiz
    if row.party_type and row.party:
        party_name = get_party_name(row.party_type, row.party)
        display_name = party_name or row.party
        is_kirim = flt(row.debit_in_account_currency) > 0
        suffix = "Приход" if is_kirim else "Расход"
        category = get_category_from_party_type(row.party_type)
        return {
            "description": f"{display_name} ({suffix})",
            "category": category,
        }

    # 2. Payment Entry — PE dan party info olish
    if row.voucher_type == "Payment Entry" and row.voucher_no in pe_info:
        pe = pe_info[row.voucher_no]
        if pe.party_type and pe.party:
            party_name = get_party_name(pe.party_type, pe.party)
            display_name = party_name or pe.party

            if pe.payment_type == "Receive":
                return {
                    "description": f"{display_name} (Приход)",
                    "category": get_category_from_party_type(pe.party_type),
                }
            elif pe.payment_type == "Pay":
                return {
                    "description": f"{display_name} (Расход)",
                    "category": get_category_from_party_type(pe.party_type),
                }
            elif pe.payment_type == "Internal Transfer":
                return {
                    "description": f"Перемещение",
                    "category": "transfer",
                }

        # Internal Transfer without party
        if pe.payment_type == "Internal Transfer":
            return {
                "description": "Перемещение",
                "category": "transfer",
            }

    # 3. Journal Entry — JE account'lardan aniqlash
    if row.voucher_type == "Journal Entry" and row.voucher_no in je_info:
        accounts = je_info[row.voucher_no]
        # Cash account bo'lmagan accountni topish (qarshi tomon)
        for acc in accounts:
            if acc.account in cash_accounts:
                continue
            if acc.party_type and acc.party:
                party_name = get_party_name(acc.party_type, acc.party)
                return {
                    "description": f"{party_name or acc.party}",
                    "category": get_category_from_party_type(acc.party_type),
                }
            if acc.root_type == "Expense":
                return {
                    "description": f"Расходы: {acc.account_name}",
                    "category": "expense",
                }
            if acc.root_type == "Equity":
                return {
                    "description": f"Дивиденды: {acc.account_name}",
                    "category": "dividend",
                }

    # 4. Against field dan aniqlash (fallback)
    if row.against:
        against_account = row.against.split(",")[0].strip() if "," in row.against else row.against

        # Cash account ga transfer?
        is_cash = frappe.db.get_value(
            "Mode of Payment Account",
            {"default_account": against_account},
            "parent"
        )
        if is_cash:
            is_kirim = flt(row.debit_in_account_currency) > 0
            direction = "из" if is_kirim else "в"
            return {
                "description": f"Перемещение {direction} {is_cash}",
                "category": "transfer",
            }

        acc_info = frappe.db.get_value(
            "Account", against_account,
            ["account_name", "root_type", "account_type"],
            as_dict=True
        )
        if acc_info:
            if acc_info.root_type == "Expense":
                return {
                    "description": f"Расходы: {acc_info.account_name}",
                    "category": "expense",
                }
            if acc_info.root_type == "Equity":
                return {
                    "description": f"Дивиденды: {acc_info.account_name}",
                    "category": "dividend",
                }
            if acc_info.account_type == "Receivable":
                return {
                    "description": acc_info.account_name,
                    "category": "customer",
                }
            if acc_info.account_type == "Payable":
                return {
                    "description": acc_info.account_name,
                    "category": "supplier",
                }
            return {
                "description": acc_info.account_name,
                "category": "other",
            }

    return {
        "description": row.voucher_no or "",
        "category": "other",
    }


def get_category_from_party_type(party_type):
    """Party type dan category"""
    mapping = {
        "Customer": "customer",
        "Supplier": "supplier",
        "Employee": "employee",
    }
    return mapping.get(party_type, "other")


def get_party_name(party_type, party):
    """Party nomini olish"""
    name_fields = {
        "Customer": "customer_name",
        "Supplier": "supplier_name",
        "Employee": "employee_name",
    }
    field = name_fields.get(party_type)
    if field:
        return frappe.db.get_value(party_type, party, field)
    return party


def get_summary_html(data):
    """Summary HTML table — kategoriyalar bo'yicha kirim/chiqim"""
    if not data or len(data) <= 1:
        return ""

    opening = 0
    customer_kirim = 0
    supplier_chiqim = 0
    expense_chiqim = 0
    dividend_chiqim = 0
    transfer_kirim = 0
    transfer_chiqim = 0
    employee_chiqim = 0
    other_kirim = 0
    other_chiqim = 0

    for row in data:
        if row.get("is_opening"):
            opening = flt(row.get("balance"))
            continue
        if row.get("is_total"):
            continue

        category = row.get("category", "other")
        kirim = flt(row.get("kirim"))
        chiqim = flt(row.get("chiqim"))

        if category == "customer":
            customer_kirim += kirim
        elif category == "supplier":
            supplier_chiqim += chiqim
        elif category == "expense":
            expense_chiqim += chiqim
        elif category == "dividend":
            dividend_chiqim += chiqim
        elif category == "transfer":
            transfer_kirim += kirim
            transfer_chiqim += chiqim
        elif category == "employee":
            employee_chiqim += chiqim
        else:
            other_kirim += kirim
            other_chiqim += chiqim

    closing = opening + customer_kirim + other_kirim + transfer_kirim - supplier_chiqim - expense_chiqim - dividend_chiqim - transfer_chiqim - employee_chiqim - other_chiqim

    def fmt(val):
        return f"{flt(val):,.2f}"

    html = f"""
    <div style="margin-top: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 5px;">
        <table style="width: 100%; border-collapse: collapse; background: white;">
            <thead>
                <tr style="background-color: #f0f0f0;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 40%;"></th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd; width: 30%; color: #388e3c; font-weight: bold;">Кирим</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd; width: 30%; color: #d32f2f; font-weight: bold;">Чиқим</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #e3f2fd;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Начальный остаток</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; font-weight: bold;" colspan="2">{fmt(opening)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">Покупатели</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{fmt(customer_kirim)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #999;">—</td>
                </tr>
                <tr style="background-color: #fafafa;">
                    <td style="padding: 10px; border: 1px solid #ddd;">Поставщики</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #999;">—</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{fmt(supplier_chiqim)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">Расходы</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #999;">—</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{fmt(expense_chiqim)}</td>
                </tr>
                <tr style="background-color: #fafafa;">
                    <td style="padding: 10px; border: 1px solid #ddd;">Дивиденды</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #999;">—</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{fmt(dividend_chiqim)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">Сотрудники</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #999;">—</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{fmt(employee_chiqim)}</td>
                </tr>
                <tr style="background-color: #fafafa;">
                    <td style="padding: 10px; border: 1px solid #ddd;">Перемещения</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{fmt(transfer_kirim)}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{fmt(transfer_chiqim)}</td>
                </tr>
                <tr style="background-color: #e3f2fd; font-weight: bold;">
                    <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Конечный остаток</td>
                    <td style="padding: 12px; border: 1px solid #ddd; text-align: right; font-weight: bold;" colspan="2">{fmt(closing)}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """

    return html
