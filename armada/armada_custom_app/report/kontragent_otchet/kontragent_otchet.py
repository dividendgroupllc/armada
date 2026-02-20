import frappe
from frappe.utils import flt

def execute(filters=None):
    if not filters:
        return [], []

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_columns(filters):
    columns = [
        {"label": "Контрагент тури", "fieldname": "party_type", "fieldtype": "Data", "width": 130},
        {"label": "Контрагент", "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 200},
        {"label": "Валюта", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
        {"label": "Акт Сверка", "fieldname": "akt_sverka_link", "fieldtype": "Data", "width": 120},
        {"label": "Кредит (дан олдин)", "fieldname": "opening_credit_usd", "fieldtype": "Currency", "width": 150},
        {"label": "Дебет (дан олдин)", "fieldname": "opening_debit_usd", "fieldtype": "Currency", "width": 150},
        {"label": "Кредит (давр)", "fieldname": "period_credit_usd", "fieldtype": "Currency", "width": 150},
        {"label": "Дебет (давр)", "fieldname": "period_debit_usd", "fieldtype": "Currency", "width": 150},
        {"label": "Сўнгги Кредит", "fieldname": "final_credit_usd", "fieldtype": "Currency", "width": 150},
        {"label": "Сўнгги Дебет", "fieldname": "final_debit_usd", "fieldtype": "Currency", "width": 150},
    ]

    return columns


def get_data(filters):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    party_type = filters.get("party_type")
    party = filters.get("party")

    parties = get_parties(party_type, party)

    data = []

    totals = {
        "opening_credit_usd": 0,
        "opening_debit_usd": 0,
        "period_credit_usd": 0,
        "period_debit_usd": 0,
        "final_credit_usd": 0,
        "final_debit_usd": 0,
    }

    for party_info in parties:
        row = calculate_party_balances(party_info, from_date, to_date)
        if row:
            data.append(row)

            for key in totals:
                totals[key] += row.get(key, 0)

    if data:
        total_row = {
            "party_type": "",
            "party": "ЖАМИ",
            "currency": "",
            "akt_sverka_link": "",
            "is_total_row": True
        }
        total_row.update(totals)
        data.insert(0, total_row)

    return data


def get_parties(party_type=None, party=None):
    """Get list of parties based on filters"""
    conditions = ["party IS NOT NULL", "party != ''", "party_type IS NOT NULL", "party_type != ''", "party_type != 'Employee'"]
    values = []

    if party:
        # Specific party
        conditions.append("party = %s")
        values.append(party)

    if party_type:
        conditions.append("party_type = %s")
        values.append(party_type)

    where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT DISTINCT party_type, party
        FROM `tabGL Entry`
        {where_clause}
        ORDER BY party_type, party
    """

    result = frappe.db.sql(query, tuple(values), as_dict=True)
    return result


def calculate_party_balances(party_info, from_date, to_date):
    """Calculate all balances for a party"""
    party_type = party_info.get("party_type")
    party = party_info.get("party")

    currency = get_party_currency(party_type, party)

    opening_usd = calculate_opening_balance(party_type, party, from_date, "USD")
    period_usd = calculate_period_balance(party_type, party, from_date, to_date, "USD")

    final_usd_net = (opening_usd['credit'] - opening_usd['debit']) + (period_usd['credit'] - period_usd['debit'])

    final_credit_usd = final_usd_net if final_usd_net > 0 else 0
    final_debit_usd = abs(final_usd_net) if final_usd_net < 0 else 0

    return {
        "party_type": party_type,
        "party": party,
        "currency": currency,
        "akt_sverka_link": "Акт Сверка",
        "opening_credit_usd": opening_usd['credit'] if opening_usd['credit'] > 0 else 0,
        "opening_debit_usd": opening_usd['debit'] if opening_usd['debit'] > 0 else 0,
        "period_credit_usd": period_usd['credit'],
        "period_debit_usd": period_usd['debit'],
        "final_credit_usd": final_credit_usd,
        "final_debit_usd": final_debit_usd,
    }


def get_party_currency(party_type, party):
    """Get party currency from Party Financial Defaults"""
    currency = frappe.db.get_value(
        "Party Financial Defaults",
        {"party_type": party_type, "party": party},
        "currency"
    )
    return currency or "USD"


def calculate_opening_balance(party_type, party, from_date, currency):
    """
    Calculate opening balance before from_date for a specific currency

    Credit calculation:
    + Journal Entry (Opening Entry) Credit
    + Purchase Invoice
    + Payment Entry Receive
    + Journal Entry (Journal Entry) Credit

    Debit calculation:
    + Journal Entry (Opening Entry) Debit
    + Sales Invoice
    + Payment Entry Pay
    + Journal Entry (Journal Entry) Debit
    """

    # Journal Entry Opening Entry Credit
    je_opening_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Opening Entry'
          )
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Journal Entry Journal Entry Credit
    je_journal_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Journal Entry'
          )
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Purchase Invoice
    pi_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Purchase Invoice'
          AND account_currency = %s
          AND is_cancelled = 0
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Payment Entry Receive
    pe_receive_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(ge.credit_in_account_currency), 0)
        FROM `tabGL Entry` ge
        INNER JOIN `tabPayment Entry` pe ON ge.voucher_no = pe.name
        WHERE ge.posting_date < %s
          AND ge.party_type = %s
          AND ge.party = %s
          AND ge.voucher_type = 'Payment Entry'
          AND pe.payment_type = 'Receive'
          AND ge.account_currency = %s
          AND ge.is_cancelled = 0
    """, (from_date, party_type, party, currency))[0][0] or 0

    total_credit = je_opening_credit + je_journal_credit + pi_credit + pe_receive_credit

    # Debit calculations
    # Journal Entry Opening Entry Debit
    je_opening_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Opening Entry'
          )
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Journal Entry Journal Entry Debit
    je_journal_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Journal Entry'
          )
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Sales Invoice
    si_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Sales Invoice'
          AND account_currency = %s
          AND is_cancelled = 0
    """, (from_date, party_type, party, currency))[0][0] or 0

    # Payment Entry Pay
    pe_pay_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(ge.debit_in_account_currency), 0)
        FROM `tabGL Entry` ge
        INNER JOIN `tabPayment Entry` pe ON ge.voucher_no = pe.name
        WHERE ge.posting_date < %s
          AND ge.party_type = %s
          AND ge.party = %s
          AND ge.voucher_type = 'Payment Entry'
          AND pe.payment_type = 'Pay'
          AND ge.account_currency = %s
          AND ge.is_cancelled = 0
    """, (from_date, party_type, party, currency))[0][0] or 0

    total_debit = je_opening_debit + je_journal_debit + si_debit + pe_pay_debit

    # Calculate net and determine credit/debit
    net = total_credit - total_debit

    if net > 0:
        return {"credit": net, "debit": 0}
    else:
        return {"credit": 0, "debit": abs(net)}


def calculate_period_balance(party_type, party, from_date, to_date, currency):
    """
    Calculate period balance from from_date to to_date for a specific currency

    Credit calculation:
    + Opening Entry Credit
    + Journal Entry Credit
    + Purchase Invoice
    + Payment Entry Receive

    Debit calculation:
    + Opening Entry Debit
    + Journal Entry Debit
    + Payment Entry Pay
    + Sales Invoice
    """

    # Opening Entry Credit
    opening_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Opening Entry'
          )
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Journal Entry Credit
    je_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Journal Entry'
          )
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Purchase Invoice Credit
    pi_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Purchase Invoice'
          AND account_currency = %s
          AND is_cancelled = 0
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Payment Entry Receive Credit
    pe_receive_credit = frappe.db.sql("""
        SELECT IFNULL(SUM(ge.credit_in_account_currency), 0)
        FROM `tabGL Entry` ge
        INNER JOIN `tabPayment Entry` pe ON ge.voucher_no = pe.name
        WHERE ge.posting_date >= %s
          AND ge.posting_date <= %s
          AND ge.party_type = %s
          AND ge.party = %s
          AND ge.voucher_type = 'Payment Entry'
          AND pe.payment_type = 'Receive'
          AND ge.account_currency = %s
          AND ge.is_cancelled = 0
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    total_credit = opening_credit + je_credit + pi_credit + pe_receive_credit

    # Debit calculations
    # Opening Entry Debit
    opening_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Opening Entry'
          )
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Journal Entry Debit
    je_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Journal Entry'
          AND account_currency = %s
          AND is_cancelled = 0
          AND voucher_no IN (
              SELECT name FROM `tabJournal Entry`
              WHERE voucher_type = 'Journal Entry'
          )
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Payment Entry Pay Debit
    pe_pay_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(ge.debit_in_account_currency), 0)
        FROM `tabGL Entry` ge
        INNER JOIN `tabPayment Entry` pe ON ge.voucher_no = pe.name
        WHERE ge.posting_date >= %s
          AND ge.posting_date <= %s
          AND ge.party_type = %s
          AND ge.party = %s
          AND ge.voucher_type = 'Payment Entry'
          AND pe.payment_type = 'Pay'
          AND ge.account_currency = %s
          AND ge.is_cancelled = 0
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    # Sales Invoice Debit
    si_debit = frappe.db.sql("""
        SELECT IFNULL(SUM(debit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND voucher_type = 'Sales Invoice'
          AND account_currency = %s
          AND is_cancelled = 0
    """, (from_date, to_date, party_type, party, currency))[0][0] or 0

    total_debit = opening_debit + je_debit + pe_pay_debit + si_debit

    return {"credit": total_credit, "debit": total_debit}
