"""Lokal test uchun long-polling rejimi.

Lokal serverga Telegram webhook yubora olmaydi, shuning uchun bu skript
update'larni getUpdates orqali o'zi olib keladi. Prod'da ishlatilmaydi.

    bench --site armada.local execute armada.armada_custom_app.telegram.polling.run

To'xtatish: Ctrl+C. Ishga tushganda webhook o'chiriladi — prod bilan bir xil
tokenni ishlatmang.
"""

import frappe
import requests

from armada.armada_custom_app.api.telegram_webhook import process_update
from armada.armada_custom_app.telegram.sender import _url, delete_webhook


def run():
    delete_webhook()
    print("Telegram polling ishga tushdi. To'xtatish: Ctrl+C", flush=True)

    offset = None
    while True:
        try:
            r = requests.get(
                _url("getUpdates"),
                params={"timeout": 30, "offset": offset},
                timeout=40,
            )
            updates = r.json().get("result", [])
        except requests.RequestException as e:
            print(f"getUpdates xato: {e}", flush=True)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            print(f"update {update['update_id']}: {list(update.keys())[1:]}", flush=True)
            try:
                process_update(update)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                frappe.log_error(frappe.get_traceback(), "Telegram polling")
                print(frappe.get_traceback(), flush=True)
