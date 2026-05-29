"""
armada_custom_app/api/pl_pdf_api.py
"""
import frappe
import json
import os

# EXACT account_name → DATA key  (console output dan olindi)
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
	"5233 - Услуги": "uslugi",
	"5234 - Канцтовар": "kantc",
	# Commercial
	"5218 - Реклама и маркетинг": "reklama",
	"5226 - Хайрия эхсон": "khairiya",
	# Tax
	"5232 - Налог на прибыль": "nalog_prib",
	# Not mapped (ignored): Round Off, Total Income, Total Expense, Profit for year
}


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

	# Dynamic column keys (oylik fieldnames)
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
	n_cols = len(col_keys)

	# Parse rows → data dict
	data = {}
	for row in rows:
		if not isinstance(row, dict):
			continue
		acct_name = str(row.get("account_name") or row.get("account") or "")
		# " - AM" suffix ni o'chir
		if " - AM" in acct_name:
			acct_name = acct_name.replace(" - AM", "").strip()

		key = ACCOUNT_KEY_MAP.get(acct_name)
		if not key:
			code = acct_name.split(" - ")[0].strip()
			for map_name, map_key in ACCOUNT_KEY_MAP.items():
				if map_name.split(" - ")[0].strip() == code:
					key = map_key
					break

		values = [float(row.get(ck) or 0) for ck in col_keys]
		data[key] = values

	# PDF yaratish
	from armada.armada_custom_app.pdf_engine.pl_pdf import generate

	company = normalized.get("company", "report").replace(" ", "_")
	start = normalized.get("period_start_date", "")[:7]
	end = normalized.get("period_end_date", "")[:7]
	filename = f"PL_{company}_{start}_to_{end}.pdf"

	output_path = generate(data, filename, col_keys=col_keys)

	# Frappe File doc
	site_path = frappe.get_site_path("private", "files", filename)
	if not os.path.exists(site_path):
		import shutil
		shutil.copy(output_path, site_path)

	# Eski faylni o'chir (duplicate oldini olish)
	existing = frappe.db.exists("File", {"file_name": filename})
	if existing:
		frappe.delete_doc("File", existing, ignore_permissions=True)

	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": filename,
		"file_url": f"/private/files/{filename}",
		"is_private": 1,
		"folder": "Home/Attachments",
	})
	file_doc.flags.ignore_permissions = True
	file_doc.insert()

	return {
		"file_url": file_doc.file_url,
		"file_name": filename,
	}


def _normalize_filters(f):
	return {
		"company": f.get("company"),
		"filter_based_on": f.get("filter_based_on", "Date Range"),
		"period_start_date": f.get("period_start_date"),
		"period_end_date": f.get("period_end_date"),
		"from_fiscal_year": f.get("from_fiscal_year"),
		"to_fiscal_year": f.get("to_fiscal_year"),
		"periodicity": f.get("periodicity", "Monthly"),
		"accumulated_values": int(f.get("accumulated_values", 0)),
		"include_default_book_entries": int(
			f.get("include_default_book_entries", 1)),
	}
