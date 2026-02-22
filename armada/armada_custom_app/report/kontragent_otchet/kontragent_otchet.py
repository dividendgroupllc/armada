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
        data.append(total_row)  # JAMI oxirgi qatorda

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

    opening = calculate_opening_balance(party_type, party, from_date)
    period = calculate_period_balance(party_type, party, from_date, to_date)

    opening_net = flt(opening['credit'] - opening['debit'], 2)
    period_net = flt(period['credit'] - period['debit'], 2)
    final_net = flt(opening_net + period_net, 2)

    return {
        "party_type": party_type,
        "party": party,
        "currency": currency,
        "akt_sverka_link": "Акт Сверка",
        "opening_credit_usd": opening_net if opening_net > 0 else 0,
        "opening_debit_usd": abs(opening_net) if opening_net < 0 else 0,
        "period_credit_usd": flt(period['credit'], 2),
        "period_debit_usd": flt(period['debit'], 2),
        "final_credit_usd": final_net if final_net > 0 else 0,
        "final_debit_usd": abs(final_net) if final_net < 0 else 0,
    }


def get_party_currency(party_type, party):
    """Get party currency from GL Entry (most recent transaction currency)"""
    currency = frappe.db.sql("""
        SELECT account_currency
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND is_cancelled = 0
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, (party_type, party))
    return currency[0][0] if currency else "USD"


def calculate_opening_balance(party_type, party, from_date):
    """Calculate opening balance before from_date — all GL entries for the party"""
    result = frappe.db.sql("""
        SELECT
            IFNULL(SUM(credit_in_account_currency), 0) as credit,
            IFNULL(SUM(debit_in_account_currency), 0) as debit
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND is_cancelled = 0
    """, (from_date, party_type, party), as_dict=True)[0]

    return {"credit": flt(result.credit, 2), "debit": flt(result.debit, 2)}


def calculate_period_balance(party_type, party, from_date, to_date):
    """Calculate period balance from from_date to to_date — all GL entries for the party"""
    result = frappe.db.sql("""
        SELECT
            IFNULL(SUM(credit_in_account_currency), 0) as credit,
            IFNULL(SUM(debit_in_account_currency), 0) as debit
        FROM `tabGL Entry`
        WHERE posting_date >= %s
          AND posting_date <= %s
          AND party_type = %s
          AND party = %s
          AND is_cancelled = 0
    """, (from_date, to_date, party_type, party), as_dict=True)[0]

    return {"credit": flt(result.credit, 2), "debit": flt(result.debit, 2)}
