# Ba'zi foydalanuvchilar (Administrator, omborchi@, ishlabchiqarish@) jadval
# ustunlarini shaxsiy sozlab olgan — ularda yangi "Остаток на дату" ustuni
# ko'rinmaydi. Shaxsiy GridView sozlamasini tozalaymiz: hamma standart
# (bir xil) ustunlarni ko'radi. Qolgan shaxsiy sozlamalar (filtr, saralash,
# oxirgi ko'rinish) saqlanadi.
import json

import frappe

PARENTS = (
	"Purchase Receipt",
	"Purchase Invoice",
	"Delivery Note",
	"Sales Invoice",
	"Stock Entry",
)


def execute():
	rows = frappe.db.sql(
		"select `user`, `doctype`, `data` from `__UserSettings` where `doctype` in %s",
		(PARENTS,),
		as_dict=True,
	)
	for row in rows:
		try:
			data = json.loads(row.data or "{}")
		except Exception:
			continue
		if not isinstance(data, dict) or "GridView" not in data:
			continue

		data.pop("GridView", None)
		frappe.db.sql(
			"update `__UserSettings` set `data`=%s where `user`=%s and `doctype`=%s",
			(json.dumps(data), row.user, row.doctype),
		)
		# redis keshini ham tozalaymiz, aks holda eski sozlama qaytib keladi
		frappe.cache.hdel("_user_settings", f"{row.doctype}::{row.user}")
