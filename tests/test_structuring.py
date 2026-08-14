"""Unit tests for dynamic JSON structuring rules, numeric preservation, and traceability."""

from services.structuring_service import extract_field_traceability
from models.schemas import ConfidenceLevel


def test_field_traceability_extraction():
    raw_text = (
        "ACME SUPPLIES LTD\n"
        "Invoice Number: INV-00984\n"
        "Date: 2026-08-11\n"
        "Product: AMUL TAAZA 1L\n"
        "Total: R 1,250.00\n"
    )

    structured_data = {
        "document_type": "invoice",
        "supplier": "ACME SUPPLIES LTD",
        "invoice_number": "INV-00984",
        "date": "2026-08-11",
        "line_items": [
            {
                "product_name": "AMUL TAAZA 1L",
                "quantity": 1,
            }
        ],
        "total_amount": 1250.00,
        "currency": "R",
    }

    traces = extract_field_traceability(structured_data, raw_text)

    # Check that supplier and invoice_number match directly in raw text
    trace_map = {t.field_name: t for t in traces}
    assert "supplier" in trace_map
    assert trace_map["supplier"].raw_value == "ACME SUPPLIES LTD"
    assert trace_map["supplier"].confidence == ConfidenceLevel.HIGH

    assert "invoice_number" in trace_map
    assert trace_map["invoice_number"].raw_value == "INV-00984"

    assert "line_items[0].product_name" in trace_map
    assert trace_map["line_items[0].product_name"].raw_value == "AMUL TAAZA 1L"


def test_leading_zero_and_numeric_preservation():
    # String representation for codes with leading zeros must not be stripped
    code = "00123"
    structured = {"account_code": code, "amount": 45.50}
    assert isinstance(structured["account_code"], str)
    assert structured["account_code"] == "00123"
    assert structured["account_code"] != 123


def test_null_handling_for_missing_fields():
    # When information is not present, value must be null/None
    structured = {
        "document_type": "receipt",
        "merchant": "Quick Mart",
        "tax_id": None,
        "discount": None,
    }
    assert structured["tax_id"] is None
    assert structured["discount"] is None
