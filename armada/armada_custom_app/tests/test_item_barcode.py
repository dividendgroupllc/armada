from unittest import TestCase
from unittest.mock import patch

import frappe

from armada.armada_custom_app import barcode


class ItemDocStub:
    def __init__(self, barcodes=None, stock_uom="Nos"):
        self.barcodes = barcodes or []
        self.stock_uom = stock_uom

    def get(self, fieldname, default=None):
        return getattr(self, fieldname, default)

    def append(self, fieldname, value):
        getattr(self, fieldname).append(frappe._dict(value))

    def set(self, fieldname, value):
        setattr(self, fieldname, value)


class TestItemBarcode(TestCase):
    @patch("armada.armada_custom_app.barcode.frappe.get_meta")
    @patch("armada.armada_custom_app.barcode.generate_item_barcode")
    def test_ensure_item_barcode_adds_arm_barcode(self, generate_item_barcode, get_meta):
        get_meta.return_value.has_field.return_value = True
        generate_item_barcode.return_value = "ARM0000000001"
        doc = ItemDocStub()

        barcode.ensure_item_barcode(doc)

        self.assertEqual(doc.barcodes[0].barcode, "ARM0000000001")
        self.assertEqual(doc.barcodes[0].uom, "Nos")
        self.assertEqual(doc.custom_barcode, "ARM0000000001")

    @patch("armada.armada_custom_app.barcode.frappe.get_meta")
    @patch("armada.armada_custom_app.barcode.generate_item_barcode")
    def test_ensure_item_barcode_keeps_existing_barcode(self, generate_item_barcode, get_meta):
        get_meta.return_value.has_field.return_value = True
        doc = ItemDocStub(barcodes=[frappe._dict(barcode="MANUAL-001", uom="Nos")])

        barcode.ensure_item_barcode(doc)

        generate_item_barcode.assert_not_called()
        self.assertEqual(len(doc.barcodes), 1)
        self.assertEqual(doc.barcodes[0].barcode, "MANUAL-001")
        self.assertEqual(doc.custom_barcode, "MANUAL-001")
