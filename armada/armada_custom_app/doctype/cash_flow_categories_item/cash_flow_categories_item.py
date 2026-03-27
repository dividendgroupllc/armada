# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CashFlowCategoriesItem(Document):
	pass


import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_indirect_accounts(doctype, txt, searchfield, start, page_len, filters):
	# 'Indirect Expenses' nomli guruhni topamiz (istalgan kompaniya prefiksi bilan)
	parent_info = frappe.db.get_value(
		"Account",
		{"account_name": "Indirect Expenses", "is_group": 1},
		["lft", "rgt"],
		as_dict=True
	)

	if not parent_info:
		return []

	return frappe.db.sql("""
		SELECT name, parent_account
		FROM `tabAccount`
		WHERE lft > %s AND rgt < %s
		  AND is_group = 0
		  AND (name LIKE %s OR parent_account LIKE %s)
		LIMIT %s OFFSET %s
	""", (parent_info.lft, parent_info.rgt, f"%{txt}%", f"%{txt}%", page_len, start))
