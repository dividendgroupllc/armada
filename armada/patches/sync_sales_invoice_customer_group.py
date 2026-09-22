"""
Sync `customer_group` on submitted Sales Invoices with the customer's current group.

`customer_group` on Sales Invoice is a snapshot taken from the Customer master
at the time the invoice was created/saved — it does not update automatically
when a customer is later moved to a different Customer Group (e.g. tagging
existing customers as "Instagram"). Old invoices keep the stale value, often
blank on invoices saved before the field was populated at all.

The "Gross Profit" report (group_by = Customer) reads this stored field, not
the customer's live group, so a newly (re)grouped customer shows up with a
blank Customer Group and can't be filtered by it.

Backfills every submitted Sales Invoice whose `customer_group` doesn't match
its customer's current group. Metadata only — doesn't touch GL entries, stock,
or totals, so a direct SQL update is safe (no need to go through doc.save()).

Idempotent: re-running only touches rows still out of sync.
"""
import frappe


def execute():
    frappe.db.sql(
        """
        UPDATE `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        SET si.customer_group = c.customer_group
        WHERE si.docstatus = 1
          AND c.customer_group IS NOT NULL
          AND c.customer_group != ''
          AND (si.customer_group IS NULL OR si.customer_group != c.customer_group)
        """
    )
    frappe.db.commit()
