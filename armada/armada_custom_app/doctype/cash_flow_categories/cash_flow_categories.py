# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CashFlowCategories(Document):
	def validate(self):
		self.validate_unique_accounts()

	def validate_unique_accounts(self):
		# Joriy hujjat ichida takrorlanmasligi
		seen = set()
		for row in self.direct_cash_flow or []:
			if not row.direct_expence_account:
				continue
			if row.direct_expence_account in seen:
				frappe.throw(
					_("Account {0} is duplicated in row {1}").format(
						frappe.bold(row.direct_expence_account), row.idx
					)
				)
			seen.add(row.direct_expence_account)

		# Boshqa Cash Flow Categories hujjatlarida ishlatilgan bo'lmasligi
		used = set(get_used_accounts(exclude_parent=self.name))
		for row in self.direct_cash_flow or []:
			if row.direct_expence_account and row.direct_expence_account in used:
				parent = frappe.db.get_value(
					"Cash Flow Categories Item",
					{"direct_expence_account": row.direct_expence_account, "parent": ["!=", self.name or ""]},
					"parent",
				)
				frappe.throw(
					_("Account {0} (row {1}) is already used in Cash Flow Categories {2}").format(
						frappe.bold(row.direct_expence_account), row.idx, frappe.bold(parent or "")
					)
				)


@frappe.whitelist()
def get_used_accounts(exclude_parent=None):
	filters = [["direct_expence_account", "is", "set"]]
	if exclude_parent:
		filters.append(["parent", "!=", exclude_parent])

	accounts = frappe.get_all(
		"Cash Flow Categories Item",
		filters=filters,
		pluck="direct_expence_account",
	)
	return list({a for a in accounts if a})
