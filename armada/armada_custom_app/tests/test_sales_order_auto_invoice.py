from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from armada.armada_custom_app.events import sales_order


class TestSalesOrderAutoInvoice(TestCase):
    @patch("armada.armada_custom_app.events.sales_order.make_sales_invoice")
    @patch("armada.armada_custom_app.events.sales_order.get_linked_sales_invoices")
    @patch("armada.armada_custom_app.events.sales_order._validate_marker_field")
    def test_submit_creates_auto_sales_invoice(
        self, validate_marker_field, get_linked_sales_invoices, make_sales_invoice
    ):
        doc = frappe._dict(name="SO-TEST-0001")
        invoice = Mock()
        invoice.get.return_value = [frappe._dict(item_code="ITEM-001")]

        get_linked_sales_invoices.return_value = []
        make_sales_invoice.return_value = invoice

        sales_order.on_sales_order_submit(doc)

        validate_marker_field.assert_called_once_with()
        get_linked_sales_invoices.assert_called_once_with(doc.name)
        make_sales_invoice.assert_called_once_with(doc.name, ignore_permissions=True)
        invoice.set.assert_called_once_with(sales_order.AUTO_CREATED_FIELD, 1)
        self.assertTrue(invoice.flags.ignore_permissions)
        invoice.insert.assert_called_once_with()
        invoice.submit.assert_called_once_with()

    @patch("armada.armada_custom_app.events.sales_order.get_linked_sales_invoices")
    @patch("armada.armada_custom_app.events.sales_order._validate_marker_field")
    def test_manual_invoice_blocks_auto_creation(self, validate_marker_field, get_linked_sales_invoices):
        doc = frappe._dict(name="SO-TEST-0002")
        get_linked_sales_invoices.return_value = [frappe._dict(name="ACC-SINV-0001", auto_created=0)]

        with self.assertRaises(frappe.ValidationError):
            sales_order.on_sales_order_submit(doc)

        validate_marker_field.assert_called_once_with()
        get_linked_sales_invoices.assert_called_once_with(doc.name)

    @patch("armada.armada_custom_app.events.sales_order.frappe.get_doc")
    @patch("armada.armada_custom_app.events.sales_order.get_linked_sales_invoices")
    @patch("armada.armada_custom_app.events.sales_order._validate_marker_field")
    def test_before_cancel_cancels_auto_sales_invoices(
        self, validate_marker_field, get_linked_sales_invoices, get_doc
    ):
        doc = frappe._dict(name="SO-TEST-0003")
        invoice_one = Mock()
        invoice_two = Mock()

        get_linked_sales_invoices.return_value = [
            frappe._dict(name="ACC-SINV-0002"),
            frappe._dict(name="ACC-SINV-0003"),
        ]
        get_doc.side_effect = [invoice_one, invoice_two]

        sales_order.before_sales_order_cancel(doc)

        validate_marker_field.assert_called_once_with()
        get_linked_sales_invoices.assert_called_once_with(
            doc.name, docstatus=1, auto_created_only=True
        )
        self.assertTrue(invoice_one.flags.ignore_permissions)
        self.assertTrue(invoice_two.flags.ignore_permissions)
        invoice_one.cancel.assert_called_once_with()
        invoice_two.cancel.assert_called_once_with()
