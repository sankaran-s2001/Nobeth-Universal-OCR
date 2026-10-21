"""Unit tests for JSON, CSV, and TXT export transformations."""

import json
from services.export_service import (
    create_export_bundle,
    export_to_csv,
    export_to_json,
    export_to_txt,
    flatten_nested_dict,
)


def test_flatten_nested_dict():
    nested = {
        "doc_id": "D-101",
        "customer": {
            "name": "Jane Doe",
            "address": {
                "city": "London",
                "zip": "W1A 1AA",
            },
        },
        "tags": ["urgent", "verified"],
    }
    flat = flatten_nested_dict(nested)
    assert flat["doc_id"] == "D-101"
    assert flat["customer.name"] == "Jane Doe"
    assert flat["customer.address.city"] == "London"
    assert flat["customer.address.zip"] == "W1A 1AA"
    assert flat["tags"] == "urgent, verified"


def test_export_to_csv_tabular_line_items():
    structured = {
        "document_type": "invoice",
        "invoice_number": "INV-789",
        "supplier": "Tech Supplies",
        "date": "2026-08-11",
        "items": [
            {"name": "USB-C Cable", "quantity": 3, "price": 9.99},
            {"name": "HDMI Adapter", "quantity": 1, "price": 24.50},
        ],
        "total": 54.47,
    }
    csv_str = export_to_csv(structured)
    lines = [line.strip() for line in csv_str.strip().splitlines() if line.strip()]

    # Header + 2 data rows
    assert len(lines) == 3
    assert "invoice_number" in lines[0]
    assert "items.name" in lines[0] or "name" in lines[0]
    assert "USB-C Cable" in lines[1]
    assert "HDMI Adapter" in lines[2]


def test_export_to_csv_key_value_format():
    structured = {
        "document_type": "id_card",
        "full_name": "Alexander Hamilton",
        "dob": "1755-01-11",
        "id_number": "0009843",
    }
    csv_str = export_to_csv(structured)
    lines = [line.strip() for line in csv_str.strip().splitlines() if line.strip()]

    # Header (Field, Value) + 4 rows
    assert len(lines) == 5
    assert "Field,Value" in lines[0]
    assert "full_name,Alexander Hamilton" in lines[2]
    assert "id_number,0009843" in lines[4]


def test_create_export_bundle():
    data = {"doc": "note", "content": "Meeting at 3 PM"}
    raw = "Meeting at 3 PM"
    bundle = create_export_bundle(
        structured_data=data,
        raw_text=raw,
        base_filename="meeting_note.png",
        document_type="note",
        confidence="HIGH",
    )

    assert bundle.base_filename == "meeting_note"
    # JSON validation
    parsed = json.loads(bundle.json_content)
    assert parsed["content"] == "Meeting at 3 PM"

    # CSV validation
    assert "Field,Value" in bundle.csv_content

    # TXT validation
    assert "NOBETH UNIVERSAL OCR" in bundle.txt_content
    assert "Meeting at 3 PM" in bundle.txt_content


def test_export_to_csv_multiple_arrays():
    data = {
        "document_type": "invoice",
        "invoice_number": "INV-555",
        "items": [
            {"desc": "Product A", "qty": 2},
            {"desc": "Product B", "qty": 1},
        ],
        "taxes": [
            {"name": "VAT", "rate": 0.15},
        ],
    }
    csv_str = export_to_csv(data)
    lines = [line.strip() for line in csv_str.strip().splitlines() if line.strip()]

    # Header + 2 data rows
    assert len(lines) == 3
    assert "invoice_number" in lines[0]
    assert "desc" in lines[0]
    # taxes column should be preserved
    assert "taxes" in lines[0]
    assert "VAT" in lines[1]


def test_export_to_csv_multiple_arrays_preservation():
    data = {
        "invoice_number": "INV-101",
        "vendor": "ABC Store",
        "line_items": [
            {"description": "Notebook", "quantity": 2, "amount": 100},
            {"description": "Pen", "quantity": 3, "amount": 30},
        ],
        "taxes": [
            {"name": "GST", "amount": 11.70},
            {"name": "Surcharge", "amount": 2.00},
        ],
        "notes": "Sample invoice",
    }
    csv_str = export_to_csv(data)
    assert "INV-101" in csv_str
    assert "ABC Store" in csv_str
    assert "Notebook" in csv_str
    assert "Pen" in csv_str
    assert "GST" in csv_str
    assert "Surcharge" in csv_str
    assert "Sample invoice" in csv_str


def test_export_to_csv_edge_cases_and_unicode():
    data = {
        "invoice_number": "INV-€999",
        "customer": {"name": "François Müller", "notes": None},
        "empty_items": [],
        "line_items": [
            {"item": "Café au lait", "price": "€4.50", "discount": None},
        ],
    }
    csv_str = export_to_csv(data)
    assert "INV-€999" in csv_str
    assert "François Müller" in csv_str
    assert "Café au lait" in csv_str
    assert "€4.50" in csv_str
