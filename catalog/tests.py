from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.utils import translation
from openpyxl import Workbook

from catalog import imports
from catalog.models import Product


def workbook_bytes(rows, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or [str(label) for _key, label in imports.PRODUCT_COLUMNS])
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


class ProductImportTests(TestCase):
    def test_new_rows_are_previewed_not_written(self):
        stream = workbook_bytes([["PRD-1", "Kit A", "Acme", 100, "50.00", "20", ""]])
        preview = imports.parse_workbook(stream, "product")
        self.assertFalse(preview.blocked)
        self.assertEqual(len(preview.creates), 1)
        self.assertEqual(Product.objects.count(), 0)

    def test_duplicate_code_in_the_file_stops_the_whole_import(self):
        stream = workbook_bytes([
            ["PRD-1", "Kit A", "Acme", 100, "50.00", "20", ""],
            ["PRD-2", "Kit B", "Acme", 100, "60.00", "20", ""],
            ["PRD-1", "Kit C", "Acme", 100, "70.00", "20", ""],
        ])
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)
        self.assertEqual(len(preview.duplicates), 1)
        self.assertEqual(Product.objects.count(), 0)

    def test_existing_code_is_classified_as_an_update_with_a_diff(self):
        Product.objects.create(
            code="PRD-1", name="Kit A", brand="Acme", tests_per_pack=100,
            base_price_usd=Decimal("50.00"), vat_rate=Decimal("20.00"),
        )
        stream = workbook_bytes([["PRD-1", "Kit A", "Acme", 100, "75.00", "20", ""]])
        preview = imports.parse_workbook(stream, "product")
        self.assertEqual(len(preview.updates), 1)
        changes = preview.updates[0].changes
        with translation.override("en"):
            labels = [str(label) for label, _old, _new in changes]
        # Only the price differs; 20 and 20.00 must not read as a change.
        self.assertEqual(labels, ["List price (USD)"])
        self.assertEqual(changes[0][1], Decimal("50.00"))
        self.assertEqual(changes[0][2], Decimal("75.00"))

    def test_invalid_number_is_reported_as_an_error(self):
        stream = workbook_bytes([["PRD-1", "Kit A", "Acme", 100, "abc", "20", ""]])
        preview = imports.parse_workbook(stream, "product")
        self.assertTrue(preview.blocked)

    def test_confirmed_preview_writes_the_rows(self):
        stream = workbook_bytes([
            ["PRD-1", "Kit A", "Acme", 100, "50.00", "20", ""],
            ["PRD-2", "Kit B", "Nordis", 50, "80.00", "10", ""],
        ])
        preview = imports.parse_workbook(stream, "product")
        result = imports.apply_preview(preview)
        self.assertEqual(result, {"created": 2, "updated": 0})
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(
            Product.objects.get(code="PRD-2").base_price_usd, Decimal("80.00")
        )

    def test_template_download_has_the_expected_headers(self):
        payload = imports.build_template("product")
        self.assertTrue(payload.startswith(b"PK"))
