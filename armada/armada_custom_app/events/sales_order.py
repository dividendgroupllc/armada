import frappe
from frappe import _

from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice


AUTO_CREATED_FIELD = "custom_auto_created_from_sales_order"


def on_sales_order_submit(doc, method=None):
    _validate_marker_field()

    linked_invoices = get_linked_sales_invoices(doc.name)
    manual_invoices = [invoice.name for invoice in linked_invoices if not invoice.auto_created]
    auto_invoices = [invoice.name for invoice in linked_invoices if invoice.auto_created]

    if manual_invoices:
        formatted_names = ", ".join(manual_invoices)
        frappe.throw(
            _("Sales Invoice already exists for Sales Order {0}: {1}").format(doc.name, formatted_names)
        )

    if auto_invoices:
        return

    sales_invoice = make_sales_invoice(doc.name, ignore_permissions=True)
    if not sales_invoice.get("items"):
        frappe.throw(_("No invoiceable items found for Sales Order {0}").format(doc.name))

    if doc.transaction_date:
        sales_invoice.posting_date = doc.transaction_date
        sales_invoice.set_posting_time = 1
        if hasattr(sales_invoice, "due_date"):
            sales_invoice.due_date = None

    sales_invoice.set(AUTO_CREATED_FIELD, 1)
    sales_invoice.flags.ignore_permissions = True
    sales_invoice.insert()
    sales_invoice.submit()


def before_sales_order_cancel(doc, method=None):
    _validate_marker_field()

    for invoice in get_linked_sales_invoices(doc.name, docstatus=1, auto_created_only=True):
        sales_invoice = frappe.get_doc("Sales Invoice", invoice.name)
        sales_invoice.flags.ignore_permissions = True
        sales_invoice.cancel()

    for (dn_name,) in get_linked_delivery_notes(doc.name, docstatus=1):
        delivery_note = frappe.get_doc("Delivery Note", dn_name)
        delivery_note.flags.ignore_permissions = True
        delivery_note.cancel()


def get_linked_sales_invoices(sales_order_name, docstatus=None, auto_created_only=False):
    conditions = ["sii.sales_order = %(sales_order)s", "si.docstatus < 2"]
    if docstatus is not None:
        conditions.append("si.docstatus = %(docstatus)s")

    if auto_created_only:
        conditions.append(f"COALESCE(si.`{AUTO_CREATED_FIELD}`, 0) = 1")

    filters = {"sales_order": sales_order_name}
    if docstatus is not None:
        filters["docstatus"] = docstatus

    return frappe.db.sql(
        f"""
        SELECT DISTINCT
            si.name,
            COALESCE(si.`{AUTO_CREATED_FIELD}`, 0) AS auto_created
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {" AND ".join(conditions)}
        ORDER BY si.creation ASC
        """,
        filters,
        as_dict=True,
    )


def get_linked_delivery_notes(sales_order_name, docstatus=1):
    return frappe.db.sql(
        """
        SELECT DISTINCT dn.name
        FROM `tabDelivery Note` dn
        INNER JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE dni.against_sales_order = %(sales_order)s
            AND dn.docstatus = %(docstatus)s
        ORDER BY dn.creation ASC
        """,
        {"sales_order": sales_order_name, "docstatus": docstatus},
        as_list=True,
    )


def _validate_marker_field():
    if frappe.get_meta("Sales Invoice").has_field(AUTO_CREATED_FIELD):
        return

    frappe.throw(
        _("Missing custom field {0} on Sales Invoice. Run migrate/reload fixtures first.").format(
            AUTO_CREATED_FIELD
        )
    )
