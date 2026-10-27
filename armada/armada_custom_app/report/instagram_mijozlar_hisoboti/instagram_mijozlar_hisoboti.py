# Copyright (c) 2026, Armada and contributors
# For license information, please see license.txt

"""
Instagram Mijozlar Hisoboti
===========================
Customer Group = "Инстаграм" mijozlari kesimida: nechta tovar sotilgan, qanday
tovarlar, qancha puli tushgan va qancha qarz qolgan.

- Sotuv: Sales Invoice Item (docstatus = 1), qaytarishlar manfiy bo'lib ayiriladi.
- To'langan: davr ichidagi Payment Entry (GL Entry, party_type = Customer).
  To'lovlar odatda aniq invoysga bog'lanmaydi, shuning uchun Sales Invoice'ning
  outstanding_amount'i ishonchsiz — qarz GL bo'yicha mijoz balansidan olinadi.
- Invoys qatorida: Payment Ledger Entry bo'yicha ("Охирги сана"гача) — shu invoysga
  bog'langan to'lovlar, qaytarishlar va credit note JE'lar; qarz = invoys qoldig'i.
  Invoysga bog'lanmagan to'lov/kreditlar eng eski invoyslardan boshlab FIFO yopadi.
  GL Entry ishlatilmaydi: Payment Reconciliation keyin bog'laganda GL'dagi
  against_voucher yangilanmaydi, faqat PLE yangilanadi.
- Qarz: "Охирги сана"гача бўлган мижоз балансы (debit - credit), davrdan oldingi
  qoldiq ham kiradi.
- "Қарз" filtri yoki "Қарздорлар" (> 3) belgilansa: faqat qarzi shu summadan katta
  invoyslar chiqadi; mijoz qatori shu invoyslar yig'indisi bo'ladi.

Natija daraxt ko'rinishida: mijoz qatori -> uning tovarlari.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, today

DEFAULT_GROUP = "Инстаграм"
# "Қарздорлар": shu summagacha bo'lgan qoldiq yopilgan deb olinadi
DEBTOR_THRESHOLD = 3


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.to_date:
		filters.to_date = today()
	if not filters.from_date:
		filters.from_date = add_months(filters.to_date, -1)
	if getdate(filters.from_date) > getdate(filters.to_date):
		filters.from_date, filters.to_date = filters.to_date, filters.from_date
	filters.customer_group = filters.customer_group or DEFAULT_GROUP

	return get_columns(), get_data(filters)


def get_columns():
	return [
		# Daraxt strelkasi har doim birinchi ustunda chiqadi — shuning uchun Mijoz/Tovar birinchi
		{"label": _("Мижоз / Товар"), "fieldname": "name", "fieldtype": "Data", "width": 260},
		{"label": _("ID"), "fieldname": "crm_id", "fieldtype": "Data", "width": 140},
		{"label": _("Сана"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Миқдор"), "fieldname": "qty", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Сотилди"), "fieldname": "sold", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Тўланди"), "fieldname": "paid", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Қарз"), "fieldname": "debt", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Тўлов %"), "fieldname": "paid_pct", "fieldtype": "Percent", "precision": 2, "width": 80},
		{"label": _("Комментарий"), "fieldname": "comment", "fieldtype": "Small Text", "width": 320},
		{"label": _("Касса комментарий"), "fieldname": "kassa_comment", "fieldtype": "Small Text", "width": 260},
		{"label": _("Валюта"), "fieldname": "currency", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	customers = frappe.get_all(
		"Customer",
		filters={"customer_group": filters.customer_group, **({"name": filters.customer} if filters.customer else {})},
		pluck="name",
	)
	if not customers:
		return []
	filters.customers = tuple(customers)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency") if filters.company else None

	item_conditions = [
		"si.docstatus = 1",
		"si.customer IN %(customers)s",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	if filters.company:
		item_conditions.append("si.company = %(company)s")
	if filters.item_group:
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
		item_conditions.append(
			f"sii.item_group IN (SELECT name FROM `tabItem Group` WHERE lft >= {int(lft)} AND rgt <= {int(rgt)})"
		)
	if not filters.include_returns:
		item_conditions.append("si.is_return = 0")

	items = frappe.db.sql(
		f"""
		SELECT si.customer, si.name AS invoice, si.posting_date, si.custom_komment AS comment, si.custom_crm_id AS crm_id,
			sii.item_code, sii.item_name,
			SUM(sii.qty) AS qty, SUM(sii.base_net_amount) AS sold
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {" AND ".join(item_conditions)}
		GROUP BY si.name, sii.item_code, sii.item_name
		ORDER BY si.customer, si.posting_date DESC, si.posting_time DESC, si.name DESC, sold DESC
		""",
		filters,
		as_dict=True,
	)

	gl_company = "AND company = %(company)s" if filters.company else ""
	paid = dict(
		frappe.db.sql(
			f"""
			SELECT party, SUM(credit - debit)
			FROM `tabGL Entry`
			WHERE is_cancelled = 0 AND party_type = 'Customer' AND party IN %(customers)s
				AND voucher_type = 'Payment Entry'
				AND posting_date BETWEEN %(from_date)s AND %(to_date)s {gl_company}
			GROUP BY party
			""",
			filters,
		)
	)
	debt = dict(
		frappe.db.sql(
			f"""
			SELECT party, SUM(debit - credit)
			FROM `tabGL Entry`
			WHERE is_cancelled = 0 AND party_type = 'Customer' AND party IN %(customers)s
				AND posting_date <= %(to_date)s {gl_company}
			GROUP BY party
			""",
			filters,
		)
	)

	invoice_ledger = get_invoice_ledger(filters)
	invoice_names = tuple({r.invoice for r in items}) or ("",)

	# Kassa Komment Sales Order'da turadi (tasdiqlangandan keyin ham o'zgarishi mumkin) —
	# invoysga ko'chirilmaydi, shu yerda zakaz orqali olinadi
	kassa_comments = {}
	for r in frappe.db.sql(
		"""
		SELECT DISTINCT sii.parent AS invoice, so.custom_kassa_komment AS comment
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Order` so ON so.name = sii.sales_order
		WHERE sii.parent IN %(invoices)s AND IFNULL(so.custom_kassa_komment, '') != ''
		ORDER BY sii.parent, so.name
		""",
		{"invoices": invoice_names},
		as_dict=True,
	):
		comment = r.comment.strip()
		if comment and comment not in kassa_comments.setdefault(r.invoice, []):
			kassa_comments[r.invoice].append(comment)

	min_debt = flt(filters.min_debt)
	if filters.only_debtors:
		min_debt = max(min_debt, DEBTOR_THRESHOLD)
	if min_debt > 0:
		items = [
			r for r in items if r.invoice in invoice_ledger and flt(invoice_ledger[r.invoice].outstanding) > min_debt
		]

	by_customer = {}
	for row in items:
		by_customer.setdefault(row.customer, {}).setdefault(row.invoice, []).append(row)

	data = []
	total = frappe._dict(qty=0, sold=0, paid=0, debt=0)
	# Davrda harakati bor yoki qarzi bor mijozlar
	for customer in sorted(customers):
		invoices = by_customer.get(customer, {})
		rows = [r for lines in invoices.values() for r in lines]
		c_paid, c_debt = paid.get(customer) or 0, debt.get(customer) or 0
		if min_debt > 0:
			# Mijoz qatori faqat filtrdan o'tgan invoyslardan yig'iladi
			if not rows:
				continue
			c_paid = sum(flt(invoice_ledger[i].paid) for i in invoices)
			c_debt = sum(flt(invoice_ledger[i].outstanding) for i in invoices)
		if not rows and not c_paid and not c_debt:
			continue
		qty = sum(r.qty for r in rows)
		sold = sum(r.sold for r in rows)
		# Mijoz qatorida har bir ID o'z invoysiga link bo'ladi (JS formatter)
		crm_links = [
			{"crm_id": lines[0].crm_id.strip(), "invoice": invoice}
			for invoice, lines in invoices.items()
			if (lines[0].crm_id or "").strip()
		]
		data.append(
			{
				"crm_id": ", ".join(link["crm_id"] for link in crm_links),
				"crm_links": crm_links,
				"name": customer,
				"parent_row": None,
				"indent": 0,
				"qty": qty,
				"sold": sold,
				"paid": c_paid,
				"debt": c_debt,
				"paid_pct": (c_paid / sold * 100) if sold > 0 else 0,
				"currency": currency,
				"bold": 1,
			}
		)
		for invoice, lines in invoices.items():
			head = lines[0]
			inv_row = f"{customer}::{invoice}"
			inv_sold = sum(r.sold for r in lines)
			ledger = invoice_ledger.get(invoice) or frappe._dict(paid=0, outstanding=inv_sold)
			inv_paid = ledger.paid or 0
			data.append(
				{
					"crm_id": (head.crm_id or "").strip(),
					"crm_links": [{"crm_id": head.crm_id.strip(), "invoice": invoice}] if (head.crm_id or "").strip() else [],
					"name": inv_row,
					"label": invoice,
					"invoice": invoice,
					"posting_date": head.posting_date,
					"parent_row": customer,
					"indent": 1,
					"qty": sum(r.qty for r in lines),
					"sold": inv_sold,
					"paid": inv_paid,
					"debt": max(ledger.outstanding or 0, 0),
					"paid_pct": (inv_paid / inv_sold * 100) if inv_sold > 0 else 0,
					"comment": (head.comment or "").strip(),
					"kassa_comment": "; ".join(kassa_comments.get(invoice, [])),
					"currency": currency,
				}
			)
			for r in lines:
				data.append(
					{
						"name": f"{inv_row}::{r.item_code}",
						"label": r.item_name,
						"parent_row": inv_row,
						"indent": 2,
						"qty": r.qty,
						"sold": r.sold,
						"currency": currency,
					}
				)
		total.qty += qty
		total.sold += sold
		total.paid += c_paid
		total.debt += c_debt

	if data:
		data.append(
			{
				"name": _("Жами"),
				"parent_row": None,
				"indent": 0,
				"qty": total.qty,
				"sold": total.sold,
				"paid": total.paid,
				"debt": total.debt,
				"paid_pct": (total.paid / total.sold * 100) if total.sold > 0 else 0,
				"currency": currency,
				"bold": 1,
			}
		)
	return data


def get_invoice_ledger(filters):
	"""Invoys -> {paid, outstanding}, PLE bo'yicha "Охирги сана"гача.

	To'lovlar ko'pincha invoysga bog'lanmaydi (PLE'da o'ziga bog'langan avans bo'lib
	turadi) — bunday kreditlar va manfiy qoldiqli invoyslar (bog'lanmagan qaytarish,
	ortiqcha to'lov) eng eski ochiq invoyslarni FIFO yopadi. Bog'langan to'lovlar
	(Payment Reconciliation) o'z invoysida qoladi.
	"""
	ple_company = "AND company = %(company)s" if filters.company else ""
	rows = frappe.db.sql(
		f"""
		SELECT party, against_voucher_type, against_voucher_no,
			SUM(amount) AS outstanding,
			-SUM(CASE WHEN voucher_no != against_voucher_no THEN amount ELSE 0 END) AS paid,
			MIN(posting_date) AS posting_date
		FROM `tabPayment Ledger Entry`
		WHERE delinked = 0 AND party_type = 'Customer' AND party IN %(customers)s
			AND posting_date <= %(to_date)s {ple_company}
		GROUP BY party, against_voucher_type, against_voucher_no
		ORDER BY posting_date, against_voucher_no
		""",
		filters,
		as_dict=True,
	)

	ledger, credit = {}, {}
	for r in rows:
		if r.against_voucher_type == "Sales Invoice" and flt(r.outstanding) > 0:
			ledger[r.against_voucher_no] = frappe._dict(
				party=r.party, paid=flt(r.paid), outstanding=flt(r.outstanding)
			)
		else:
			if r.against_voucher_type == "Sales Invoice":
				ledger[r.against_voucher_no] = frappe._dict(party=r.party, paid=flt(r.paid), outstanding=0)
			credit[r.party] = credit.get(r.party, 0) - flt(r.outstanding)

	# rows posting_date bo'yicha tartiblangan — ledger ham eski invoysdan boshlanadi
	for inv in ledger.values():
		available = credit.get(inv.party, 0)
		if available <= 0 or inv.outstanding <= 0:
			continue
		applied = min(available, inv.outstanding)
		inv.outstanding -= applied
		inv.paid += applied
		credit[inv.party] = available - applied
	return ledger
