"""Excel import for the product catalogue and the dealer account cards.

Rules from the specification:

* A code that appears more than once **in the uploaded file** aborts the whole
  import — nothing is written and the offending rows are listed.
* Every other row is classified as *new* or *update* and shown on a preview
  screen; the write only happens after the administrator confirms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook, load_workbook

from catalog.models import Product
from dealers.models import Dealer

PRODUCT_COLUMNS = [
    ("code", _("Product code")),
    ("name", _("Product name")),
    ("brand", _("Brand")),
    ("tests_per_pack", _("Tests per pack")),
    ("base_price_usd", _("List price (USD)")),
    ("vat_rate", _("VAT rate (%)")),
    ("description", _("Description")),
]

DEALER_COLUMNS = [
    ("name", _("Dealer name")),
    ("code", _("Dealer code")),
    ("tax_no", _("Tax number")),
    ("tax_office", _("Tax office")),
    ("contact_person", _("Contact person")),
    ("phone", _("Phone")),
    ("email", _("Email")),
    ("city", _("City")),
    ("address", _("Address")),
    ("notes", _("Notes")),
]

SAMPLE_ROWS = {
    "product": [["PRD-001", "Sample reagent kit", "Acme", 100, "125.00", "20", ""]],
    "dealer": [
        ["Sample Dealer Ltd.", "D-001", "1234567890", "Kadıköy", "Jane Doe",
         "+90 216 000 00 00", "info@sampledealer.com", "İstanbul", "", ""]
    ],
}


def column_spec(kind: str):
    return PRODUCT_COLUMNS if kind == "product" else DEALER_COLUMNS


def build_template(kind: str) -> bytes:
    columns = column_spec(kind)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "template"
    sheet.append([str(label) for _key, label in columns])
    for row in SAMPLE_ROWS[kind]:
        sheet.append(row)
    for index, (_key, label) in enumerate(columns, start=1):
        sheet.column_dimensions[chr(64 + index)].width = max(len(str(label)) + 6, 18)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


@dataclass
class RowResult:
    row_no: int
    key: str
    action: str  # "create" | "update" | "error"
    values: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)  # (label, old, new)
    error: str = ""


@dataclass
class ImportPreview:
    kind: str
    rows: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Duplicate keys or invalid rows stop the whole import."""
        return bool(self.duplicates or self.errors)

    @property
    def creates(self):
        return [row for row in self.rows if row.action == "create"]

    @property
    def updates(self):
        return [row for row in self.rows if row.action == "update"]


def _to_decimal(value, label) -> Decimal:
    if value in (None, ""):
        raise ValueError(_("%(field)s is required.") % {"field": label})
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(_("%(field)s must be a number.") % {"field": label})


def _to_int(value, label) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(Decimal(str(value).replace(",", ".").strip()))
    except (InvalidOperation, ValueError):
        raise ValueError(_("%(field)s must be a whole number.") % {"field": label})


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def parse_workbook(file_obj, kind: str) -> ImportPreview:
    """Validate an uploaded workbook and classify each row."""
    preview = ImportPreview(kind=kind)
    columns = column_spec(kind)
    try:
        workbook = load_workbook(file_obj, data_only=True)
    except Exception:
        preview.errors.append(_("The file could not be read. Please upload a valid .xlsx file."))
        return preview
    sheet = workbook.active
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    if not rows:
        preview.errors.append(_("The file contains no data rows."))
        return preview

    seen: dict[str, int] = {}
    existing = _existing_keys(kind)
    for offset, raw in enumerate(rows, start=2):
        values = list(raw) + [None] * (len(columns) - len(raw))
        if all(_text(value) == "" for value in values[: len(columns)]):
            continue
        data = {key: values[index] for index, (key, _label) in enumerate(columns)}
        key = _text(data[columns[0][0]])
        if kind == "product":
            key = key.upper()
        if not key:
            preview.errors.append(
                _("Row %(row)s: %(field)s is empty.")
                % {"row": offset, "field": columns[0][1]}
            )
            continue
        if key in seen:
            preview.duplicates.append(
                _("Row %(row)s: '%(key)s' already appears on row %(first)s.")
                % {"row": offset, "key": key, "first": seen[key]}
            )
            continue
        seen[key] = offset
        try:
            cleaned = _clean_row(data, kind)
        except ValueError as exc:
            preview.errors.append(_("Row %(row)s: %(error)s") % {"row": offset, "error": exc})
            continue
        current = existing.get(key)
        if current is None:
            preview.rows.append(
                RowResult(row_no=offset, key=key, action="create", values=cleaned)
            )
        else:
            changes = _diff(current, cleaned, columns)
            preview.rows.append(
                RowResult(
                    row_no=offset,
                    key=key,
                    action="update",
                    values=cleaned,
                    changes=changes,
                )
            )
    if not preview.rows and not preview.blocked:
        preview.errors.append(_("The file contains no importable rows."))
    return preview


def _clean_row(data: dict, kind: str) -> dict:
    if kind == "product":
        return {
            "code": _text(data["code"]).upper(),
            "name": _text(data["name"]),
            "brand": _text(data["brand"]),
            "tests_per_pack": _to_int(data["tests_per_pack"], _("Tests per pack")),
            "base_price_usd": _to_decimal(data["base_price_usd"], _("List price (USD)")),
            "vat_rate": _to_decimal(data["vat_rate"], _("VAT rate (%)")),
            "description": _text(data["description"]),
        }
    return {
        "name": _text(data["name"]),
        "code": _text(data["code"]),
        "tax_no": _text(data["tax_no"]),
        "tax_office": _text(data["tax_office"]),
        "contact_person": _text(data["contact_person"]),
        "phone": _text(data["phone"]),
        "email": _text(data["email"]),
        "city": _text(data["city"]),
        "address": _text(data["address"]),
        "notes": _text(data["notes"]),
    }


def _existing_keys(kind: str) -> dict:
    if kind == "product":
        return {
            product.code.upper(): {
                "code": product.code,
                "name": product.name,
                "brand": product.brand,
                "tests_per_pack": product.tests_per_pack,
                "base_price_usd": product.base_price_usd,
                "vat_rate": product.vat_rate,
                "description": product.description,
            }
            for product in Product.objects.all()
        }
    return {
        dealer.name: {
            "name": dealer.name,
            "code": dealer.code,
            "tax_no": dealer.tax_no,
            "tax_office": dealer.tax_office,
            "contact_person": dealer.contact_person,
            "phone": dealer.phone,
            "email": dealer.email,
            "city": dealer.city,
            "address": dealer.address,
            "notes": dealer.notes,
        }
        for dealer in Dealer.objects.all()
    }


def _same(old, new) -> bool:
    """Compare two cell values, treating 20 and 20.00 as equal."""
    if isinstance(old, (Decimal, int, float)) or isinstance(new, (Decimal, int, float)):
        try:
            return Decimal(str(old or 0)) == Decimal(str(new or 0))
        except InvalidOperation:
            pass
    return str(old or "") == str(new or "")


def _diff(current: dict, new: dict, columns) -> list:
    labels = dict(columns)
    changes = []
    for key, value in new.items():
        old = current.get(key)
        if not _same(old, value):
            changes.append((labels.get(key, key), old, value))
    return changes


def apply_preview(preview: ImportPreview) -> dict:
    """Write a validated preview to the database."""
    created = updated = 0
    model = Product if preview.kind == "product" else Dealer
    lookup = "code" if preview.kind == "product" else "name"
    for row in preview.rows:
        if row.action == "create":
            model.objects.create(**row.values)
            created += 1
        elif row.action == "update":
            filter_value = row.values[lookup]
            obj = model.objects.filter(**{f"{lookup}__iexact": filter_value}).first()
            if obj is None:
                model.objects.create(**row.values)
                created += 1
                continue
            for key, value in row.values.items():
                setattr(obj, key, value)
            obj.save()
            updated += 1
    return {"created": created, "updated": updated}


def preview_to_session(preview: ImportPreview) -> dict:
    return {
        "kind": preview.kind,
        "rows": [
            {
                "row_no": row.row_no,
                "key": row.key,
                "action": row.action,
                "values": {k: str(v) for k, v in row.values.items()},
            }
            for row in preview.rows
        ],
    }


def preview_from_session(payload: dict) -> ImportPreview:
    preview = ImportPreview(kind=payload["kind"])
    for row in payload["rows"]:
        values = row["values"]
        if payload["kind"] == "product":
            values = {
                **values,
                "tests_per_pack": int(values["tests_per_pack"]),
                "base_price_usd": Decimal(values["base_price_usd"]),
                "vat_rate": Decimal(values["vat_rate"]),
            }
        preview.rows.append(
            RowResult(
                row_no=row["row_no"], key=row["key"], action=row["action"], values=values
            )
        )
    return preview
