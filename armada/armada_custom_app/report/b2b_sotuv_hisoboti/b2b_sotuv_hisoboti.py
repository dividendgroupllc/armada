# Copyright (c) 2026, Armada and contributors
# For license information, please see license.txt

"""
B2B Sotuv Hisoboti
==================
"Instagram Mijozlar Hisoboti" bilan bir xil hisobot, lekin "Инстаграм" guruhidan
(va uning ichki guruhlaridan) TASHQARI barcha mijozlar uchun. Customer Group'i bo'sh
(NULL) mijozlar ham kiradi. Hisoblash mantig'i instagram_mijozlar_hisoboti.get_data'da.
"""

import frappe

from armada.armada_custom_app.report.instagram_mijozlar_hisoboti.instagram_mijozlar_hisoboti import (
	DEFAULT_GROUP as INSTAGRAM_GROUP,
	get_columns,
	get_data,
	prepare_filters,
)


def execute(filters=None):
	filters = prepare_filters(filters)
	return get_columns(), get_data(filters, get_customers(filters))


def get_customers(filters):
	conditions, values = [], {"customer": filters.customer}
	if filters.customer:
		conditions.append("c.name = %(customer)s")

	instagram = frappe.db.get_value("Customer Group", INSTAGRAM_GROUP, ["lft", "rgt"], as_dict=True)
	if instagram:
		values.update(ig_lft=instagram.lft, ig_rgt=instagram.rgt)
		# customer_group bo'sh (NULL) mijozlar ham kiradi
		conditions.append("(cg.name IS NULL OR NOT (cg.lft >= %(ig_lft)s AND cg.rgt <= %(ig_rgt)s))")

	return frappe.db.sql_list(
		f"""
		SELECT c.name
		FROM `tabCustomer` c
		LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
		{"WHERE " + " AND ".join(conditions) if conditions else ""}
		""",
		values,
	)
