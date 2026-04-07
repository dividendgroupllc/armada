import frappe
from frappe.utils import flt

def execute(filters=None):
    if not filters:
        return [], []

    columns = get_columns()
    data = get_data(filters)

    summary_html = get_summary_html(data, filters)

    return columns, data, summary_html


def format_balance(value):
    return round(flt(value), 2) if value is not None else None


def format_qty(value):
    return round(flt(value), 2) if value is not None else None


def voucher_type_matches(row, base_voucher_type):
    voucher_type = (row or {}).get("voucher_type") or ""
    return voucher_type == base_voucher_type or voucher_type.startswith(f"{base_voucher_type} ")


def get_voucher_doctype(voucher_type):
    if not voucher_type or voucher_type in {"Boshlang'ich qoldiq", "Total"}:
        return ""

    return voucher_type.split(" (", 1)[0]


def get_columns():
    return [
        {"label": "Сана", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Ҳужжат", "fieldname": "voucher_type", "fieldtype": "Data", "width": 150},
        {"label": "Ҳужжат №", "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_doctype", "width": 120},
        {"label": "Маҳсулот номи", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": "Миқдори", "fieldname": "qty", "fieldtype": "Float", "precision": 2, "width": 80},
        {"label": "Нархи", "fieldname": "rate", "fieldtype": "Currency", "width": 100},
        {"label": "Валюта", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
        {"label": "Кредит", "fieldname": "credit", "fieldtype": "Currency", "width": 120},
        {"label": "Дебет", "fieldname": "debit", "fieldtype": "Currency", "width": 120},
        {"label": "Қолдиқ (Кред)", "fieldname": "balance_credit", "fieldtype": "Currency", "width": 120},
        {"label": "Қолдиқ (Деб)", "fieldname": "balance_debit", "fieldtype": "Currency", "width": 120},
    ]


def get_data(filters):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    party_type = filters.get("party_type")
    party = filters.get("party")

    # Party valyutasini aniqlash
    party_currency = frappe.db.sql("""
        SELECT account_currency
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND is_cancelled = 0
        ORDER BY posting_date ASC, creation ASC
        LIMIT 1
    """, (party_type, party))
    party_currency = party_currency[0][0] if party_currency else 'USD'

    # Opening balance - 1 ta query bilan hamma voucher type'larni hisoblaymiz
    opening_balance = calculate_opening_balance_optimized(
        party_type, party, party_currency, from_date
    )

    data = []

    opening_credit = opening_balance if opening_balance > 0 else 0
    opening_debit = abs(opening_balance) if opening_balance < 0 else 0

    data.append({
        "posting_date": from_date,
        "voucher_type": "Boshlang'ich qoldiq",
        "voucher_no": "",
        "item_name": "",
        "qty": None,
        "rate": None,
        "currency": party_currency,
        "credit": opening_credit,
        "debit": opening_debit,
        "balance": format_balance(opening_balance)
    })

    # GL Entry'larni olish
    gl_entries = frappe.db.sql("""
        SELECT
            gl.posting_date,
            gl.voucher_type,
            gl.voucher_no,
            gl.debit_in_account_currency as debit,
            gl.credit_in_account_currency as credit,
            gl.account_currency AS currency
        FROM `tabGL Entry` gl
        WHERE gl.posting_date BETWEEN %s AND %s
          AND gl.party_type = %s
          AND gl.party = %s
          AND gl.account_currency = %s
          AND gl.is_cancelled = 0
        ORDER BY gl.posting_date ASC, gl.creation ASC
    """, (from_date, to_date, party_type, party, party_currency), as_dict=True)

    if not gl_entries:
        finalize_data(data, to_date, party_currency, opening_balance)
        return data

    pi_vouchers = set()
    si_vouchers = set()
    pe_vouchers = set()
    je_vouchers = set()

    for gl in gl_entries:
        vt = gl.voucher_type
        if vt == "Purchase Invoice":
            pi_vouchers.add(gl.voucher_no)
        elif vt == "Sales Invoice":
            si_vouchers.add(gl.voucher_no)
        elif vt == "Payment Entry":
            pe_vouchers.add(gl.voucher_no)
        elif vt == "Journal Entry":
            je_vouchers.add(gl.voucher_no)

    # BATCH PREFETCH - barcha kerakli ma'lumotlarni oldindan yuklaymiz
    pi_items_map = {}
    pi_return_map = {}
    if pi_vouchers:
        pi_items_map = prefetch_purchase_invoice_items(pi_vouchers)
        pi_return_map = prefetch_invoice_return_status("Purchase Invoice", pi_vouchers)

    si_items_map = {}
    si_return_map = {}
    if si_vouchers:
        si_items_map = prefetch_sales_invoice_items(si_vouchers)
        si_return_map = prefetch_invoice_return_status("Sales Invoice", si_vouchers)

    pe_info_map = {}
    if pe_vouchers:
        pe_info_map = prefetch_payment_entry_info(pe_vouchers)

    je_accounts_map = {}
    if je_vouchers:
        je_accounts_map = prefetch_journal_entry_accounts(je_vouchers, party_type, party)

    balance = opening_balance

    for gl in gl_entries:
        voucher_type = gl.voucher_type
        voucher_no = gl.voucher_no

        if voucher_type == "Purchase Invoice":
            is_return = pi_return_map.get(voucher_no, 0)
            items = pi_items_map.get(voucher_no, [])
            if items:
                total_amount = sum(flt(item.get('credit', 0)) for item in items)
                for idx, item in enumerate(items):
                    is_last = (idx == len(items) - 1)
                    item_amount = flt(item.get('credit', 0))
                    if is_last:
                        balance += total_amount
                    if is_return:
                        data.append({
                            "posting_date": gl.posting_date,
                            "voucher_type": voucher_type + " (Возврат)",
                            "voucher_no": voucher_no,
                            "item_name": item.get('item_name', ''),
                            "qty": format_qty(abs(flt(item.get('qty')))),
                            "rate": item.get('rate'),
                            "currency": item.get('currency', gl.currency),
                            "credit": 0,
                            "debit": abs(item_amount),
                            "balance": format_balance(balance) if is_last else None,
                        })
                    else:
                        data.append({
                            "posting_date": gl.posting_date,
                            "voucher_type": voucher_type,
                            "voucher_no": voucher_no,
                            "item_name": item.get('item_name', ''),
                            "qty": format_qty(item.get('qty')),
                            "rate": item.get('rate'),
                            "currency": item.get('currency', gl.currency),
                            "credit": item_amount,
                            "debit": 0,
                            "balance": format_balance(balance) if is_last else None,
                        })
            else:
                if is_return:
                    balance -= flt(gl.debit)
                    data.append({
                        "posting_date": gl.posting_date,
                        "voucher_type": voucher_type + " (Возврат)",
                        "voucher_no": voucher_no,
                        "item_name": "",
                        "qty": None, "rate": None,
                        "currency": gl.currency,
                        "credit": 0, "debit": gl.debit,
                        "balance": format_balance(balance),
                    })
                else:
                    balance += flt(gl.credit)
                    data.append({
                        "posting_date": gl.posting_date,
                        "voucher_type": voucher_type,
                        "voucher_no": voucher_no,
                        "item_name": "",
                        "qty": None, "rate": None,
                        "currency": gl.currency,
                        "credit": gl.credit, "debit": 0,
                        "balance": format_balance(balance),
                    })

        elif voucher_type == "Sales Invoice":
            is_return = si_return_map.get(voucher_no, 0)
            items = si_items_map.get(voucher_no, [])
            if items:
                total_amount = sum(flt(item.get('debit', 0)) for item in items)
                for idx, item in enumerate(items):
                    is_last = (idx == len(items) - 1)
                    item_amount = flt(item.get('debit', 0))
                    if is_last:
                        balance -= total_amount
                    if is_return:
                        data.append({
                            "posting_date": gl.posting_date,
                            "voucher_type": voucher_type + " (Возврат)",
                            "voucher_no": voucher_no,
                            "item_name": item.get('item_name', ''),
                            "qty": format_qty(abs(flt(item.get('qty')))),
                            "rate": item.get('rate'),
                            "currency": item.get('currency', gl.currency),
                            "credit": abs(item_amount), "debit": 0,
                            "balance": format_balance(balance) if is_last else None,
                        })
                    else:
                        data.append({
                            "posting_date": gl.posting_date,
                            "voucher_type": voucher_type,
                            "voucher_no": voucher_no,
                            "item_name": item.get('item_name', ''),
                            "qty": format_qty(item.get('qty')),
                            "rate": item.get('rate'),
                            "currency": item.get('currency', gl.currency),
                            "credit": 0, "debit": item_amount,
                            "balance": format_balance(balance) if is_last else None,
                        })
            else:
                if is_return:
                    balance += flt(gl.credit)
                    data.append({
                        "posting_date": gl.posting_date,
                        "voucher_type": voucher_type + " (Возврат)",
                        "voucher_no": voucher_no,
                        "item_name": "",
                        "qty": None, "rate": None,
                        "currency": gl.currency,
                        "credit": gl.credit, "debit": 0,
                        "balance": format_balance(balance),
                    })
                else:
                    balance -= flt(gl.debit)
                    data.append({
                        "posting_date": gl.posting_date,
                        "voucher_type": voucher_type,
                        "voucher_no": voucher_no,
                        "item_name": "",
                        "qty": None, "rate": None,
                        "currency": gl.currency,
                        "credit": 0, "debit": gl.debit,
                        "balance": format_balance(balance),
                    })

        elif voucher_type == "Payment Entry":
            pe_info = pe_info_map.get(voucher_no, {'description': '', 'account': ''})
            balance += flt(gl.credit) - flt(gl.debit)
            data.append({
                "posting_date": gl.posting_date,
                "voucher_type": voucher_type,
                "voucher_no": voucher_no,
                "item_name": pe_info.get('description', ''),
                "qty": None, "rate": None,
                "currency": gl.currency,
                "credit": gl.credit, "debit": gl.debit,
                "balance": format_balance(balance),
            })

        elif voucher_type == "Journal Entry":
            je_accounts = je_accounts_map.get(voucher_no, [])
            if je_accounts:
                total_debit = sum(flt(acc.get('debit', 0)) for acc in je_accounts)
                total_credit = sum(flt(acc.get('credit', 0)) for acc in je_accounts)
                for idx, acc in enumerate(je_accounts):
                    is_last = (idx == len(je_accounts) - 1)
                    if is_last:
                        balance += total_credit - total_debit
                    data.append({
                        "posting_date": gl.posting_date,
                        "voucher_type": voucher_type,
                        "voucher_no": voucher_no,
                        "item_name": acc.get('account', ''),
                        "qty": None, "rate": None,
                        "currency": gl.currency,
                        "credit": acc.get('credit', 0),
                        "debit": acc.get('debit', 0),
                        "balance": format_balance(balance) if is_last else None,
                    })
            else:
                balance += flt(gl.credit) - flt(gl.debit)
                data.append({
                    "posting_date": gl.posting_date,
                    "voucher_type": voucher_type,
                    "voucher_no": voucher_no,
                    "item_name": "",
                    "qty": None, "rate": None,
                    "currency": gl.currency,
                    "credit": gl.credit, "debit": gl.debit,
                    "balance": format_balance(balance),
                })

        else:
            balance += flt(gl.credit) - flt(gl.debit)
            data.append({
                "posting_date": gl.posting_date,
                "voucher_type": voucher_type,
                "voucher_no": voucher_no,
                "item_name": "",
                "qty": None, "rate": None,
                "currency": gl.currency,
                "credit": gl.credit, "debit": gl.debit,
                "balance": format_balance(balance),
            })

    finalize_data(data, to_date, party_currency, balance)
    return data


def calculate_opening_balance_optimized(party_type, party, party_currency, from_date):
    """Opening balance - 1 ta query bilan barcha voucher type'larni hisoblaymiz"""
    result = frappe.db.sql("""
        SELECT
            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Purchase Invoice'
                THEN ge.credit_in_account_currency - ge.debit_in_account_currency
                ELSE 0
            END), 0) as pi_net,

            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Sales Invoice'
                THEN ge.debit_in_account_currency - ge.credit_in_account_currency
                ELSE 0
            END), 0) as si_net,

            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Payment Entry'
                THEN ge.credit_in_account_currency
                ELSE 0
            END), 0) as pe_credit,

            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Payment Entry'
                THEN ge.debit_in_account_currency
                ELSE 0
            END), 0) as pe_debit,

            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Journal Entry'
                THEN ge.credit_in_account_currency
                ELSE 0
            END), 0) as je_credit,

            IFNULL(SUM(CASE
                WHEN ge.voucher_type = 'Journal Entry'
                THEN ge.debit_in_account_currency
                ELSE 0
            END), 0) as je_debit

        FROM `tabGL Entry` ge
        WHERE ge.posting_date < %s
          AND ge.party_type = %s
          AND ge.party = %s
          AND ge.account_currency = %s
          AND ge.is_cancelled = 0
    """, (from_date, party_type, party, party_currency), as_dict=True)[0]

    opening_balance = (
        flt(result.pi_net) - flt(result.si_net) +
        flt(result.pe_credit) - flt(result.pe_debit) +
        flt(result.je_credit) - flt(result.je_debit)
    )

    return opening_balance


def finalize_data(data, to_date, party_currency, balance):
    if len(data) > 1:
        total_credit = sum(flt(row.get('credit', 0)) for row in data if row.get('voucher_type') != "Boshlang'ich qoldiq")
        total_debit = sum(flt(row.get('debit', 0)) for row in data if row.get('voucher_type') != "Boshlang'ich qoldiq")

        data.append({
            "posting_date": to_date,
            "voucher_type": "Total",
            "voucher_no": "",
            "item_name": "",
            "qty": None, "rate": None,
            "currency": party_currency,
            "credit": total_credit,
            "debit": total_debit,
            "balance": format_balance(balance),
        })

    for row in data:
        row['voucher_doctype'] = get_voucher_doctype(row.get('voucher_type'))
        raw_balance = row.pop('balance', None)
        if raw_balance is not None:
            v = flt(raw_balance)
            row['balance_credit'] = round(v, 2) if v > 0 else 0
            row['balance_debit'] = round(abs(v), 2) if v < 0 else 0
        else:
            row['balance_credit'] = None
            row['balance_debit'] = None



def prefetch_purchase_invoice_items(voucher_nos):
    """Barcha PI itemlarni bitta query bilan olish"""
    voucher_list = list(voucher_nos)
    items = frappe.db.sql("""
        SELECT
            pii.parent as voucher_no,
            pii.item_name,
            pii.qty,
            pii.rate,
            pi.currency,
            pii.amount as credit,
            0 as debit
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.parent IN %s
        ORDER BY pii.parent, pii.idx
    """, (voucher_list,), as_dict=True)

    result = {}
    for item in items:
        result.setdefault(item.voucher_no, []).append(item)
    return result


def prefetch_sales_invoice_items(voucher_nos):
    voucher_list = list(voucher_nos)
    items = frappe.db.sql("""
        SELECT
            sii.parent as voucher_no,
            sii.item_name,
            sii.qty,
            sii.rate,
            si.currency,
            0 as credit,
            sii.amount as debit
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.parent IN %s
        ORDER BY sii.parent, sii.idx
    """, (voucher_list,), as_dict=True)

    result = {}
    for item in items:
        result.setdefault(item.voucher_no, []).append(item)
    return result


def prefetch_invoice_return_status(doctype, voucher_nos):
    voucher_list = list(voucher_nos)
    table = "tabPurchase Invoice" if doctype == "Purchase Invoice" else "tabSales Invoice"
    rows = frappe.db.sql("""
        SELECT name, is_return
        FROM `{table}`
        WHERE name IN %s
    """.format(table=table), (voucher_list,), as_dict=True)

    return {r.name: r.is_return for r in rows}


def prefetch_payment_entry_info(voucher_nos):
    voucher_list = list(voucher_nos)
    payments = frappe.db.sql("""
        SELECT name, payment_type, paid_from, paid_to
        FROM `tabPayment Entry`
        WHERE name IN %s
    """, (voucher_list,), as_dict=True)

    result = {}
    for p in payments:
        if p.payment_type == 'Pay':
            result[p.name] = {'description': 'Pay', 'account': p.paid_from}
        elif p.payment_type == 'Receive':
            result[p.name] = {'description': 'Receive', 'account': p.paid_to}
        else:
            result[p.name] = {'description': p.payment_type, 'account': p.paid_from or p.paid_to}
    return result


def prefetch_journal_entry_accounts(voucher_nos, party_type, party):
    voucher_list = list(voucher_nos)
    accounts = frappe.db.sql("""
        SELECT
            parent as voucher_no,
            account,
            debit_in_account_currency as debit,
            credit_in_account_currency as credit
        FROM `tabJournal Entry Account`
        WHERE parent IN %s
          AND party_type = %s
          AND party = %s
        ORDER BY parent, idx
    """, (voucher_list, party_type, party), as_dict=True)

    result = {}
    for acc in accounts:
        result.setdefault(acc.voucher_no, []).append(acc)
    return result


def get_summary_html(data, filters):
    if not data or len(data) <= 1:
        return ""

    opening_row = data[0] if data else {}
    opening_balance = flt(opening_row.get('balance_credit', 0)) - flt(opening_row.get('balance_debit', 0))

    closing_balance = 0
    total_row = [r for r in data if r.get('voucher_type') == 'Total']
    if total_row:
        tr = total_row[0]
        closing_balance = flt(tr.get('balance_credit', 0)) - flt(tr.get('balance_debit', 0))
    elif data:
        lr = data[-1]
        closing_balance = flt(lr.get('balance_credit', 0)) - flt(lr.get('balance_debit', 0))

    opening_credit = opening_balance if opening_balance > 0 else 0
    opening_debit = abs(opening_balance) if opening_balance < 0 else 0

    goods_credit = sum(
        flt(r.get('credit', 0)) for r in data
        if voucher_type_matches(r, 'Purchase Invoice') or voucher_type_matches(r, 'Sales Invoice')
    )
    goods_debit = sum(
        flt(r.get('debit', 0)) for r in data
        if voucher_type_matches(r, 'Purchase Invoice') or voucher_type_matches(r, 'Sales Invoice')
    )

    money_credit = sum(
        flt(r.get('credit', 0)) for r in data
        if voucher_type_matches(r, 'Payment Entry')
    )
    money_debit = sum(
        flt(r.get('debit', 0)) for r in data
        if voucher_type_matches(r, 'Payment Entry')
    )

    accruals_credit = sum(
        flt(r.get('credit', 0)) for r in data
        if voucher_type_matches(r, 'Journal Entry')
    )
    accruals_debit = sum(
        flt(r.get('debit', 0)) for r in data
        if voucher_type_matches(r, 'Journal Entry')
    )

    closing_credit = closing_balance if closing_balance > 0 else 0
    closing_debit = abs(closing_balance) if closing_balance < 0 else 0

    html = f"""
    <div style="margin-top: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 5px;">
        <table style="width: 100%; border-collapse: collapse; background: white;">
            <thead>
                <tr style="background-color: #f0f0f0;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 40%;"></th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd; width: 30%; color: #d32f2f; font-weight: bold;">Кредит (Credit)</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd; width: 30%; color: #388e3c; font-weight: bold;">Дебет (Debit)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: 500;">Остаток на начало</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{opening_credit:,.2f}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{opening_debit:,.2f}</td>
                </tr>
                <tr style="background-color: #fafafa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: 500;">Оборот по товарам</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{goods_credit:,.2f}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{goods_debit:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: 500;">Оборот по деньгам</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{money_credit:,.2f}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{money_debit:,.2f}</td>
                </tr>
                <tr style="background-color: #fafafa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: 500;">Начисления</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #d32f2f;">{accruals_credit:,.2f}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #388e3c;">{accruals_debit:,.2f}</td>
                </tr>
                <tr style="background-color: #e3f2fd; font-weight: bold;">
                    <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Остаток на конец</td>
                    <td style="padding: 12px; border: 1px solid #ddd; text-align: right; color: #d32f2f; font-weight: bold;">{closing_credit:,.2f}</td>
                    <td style="padding: 12px; border: 1px solid #ddd; text-align: right; color: #388e3c; font-weight: bold;">{closing_debit:,.2f}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """

    return html
