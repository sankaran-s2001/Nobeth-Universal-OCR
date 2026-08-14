"""Export services: JSON formatting, intelligent CSV flattening, and TXT generation."""

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Tuple
from models.schemas import ExportBundle


def export_to_json(data: Dict[str, Any]) -> str:
    """Formats structured dictionary into indented JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def flatten_nested_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flattens nested dictionaries into dotted key paths."""
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_nested_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # If list of primitives, join as comma-separated string
            if all(not isinstance(i, (dict, list)) for i in v):
                items.append((new_key, ", ".join(str(i) for i in v)))
            else:
                # Retain list for array processing
                items.append((new_key, v))
        else:
            items.append((new_key, v))
    return dict(items)


def export_to_csv(data: Dict[str, Any]) -> str:
    """
    Intelligently flattens arbitrary dynamic JSON structures into clean CSV.
    Handles nested objects, array collections (line items/tables), and key-value forms losslessly.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # 1. Flatten dictionary
    flat = flatten_nested_dict(data)

    # 2. Identify array-of-objects fields (e.g. items, lines, rows, products, tables)
    array_fields = []
    scalar_fields = {}

    for k, v in flat.items():
        if isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
            array_fields.append((k, v))
        elif isinstance(v, list) and v and all(isinstance(i, list) for i in v):
            # Table rows as list of lists (e.g. matrix/table headers + rows)
            array_fields.append((k, v))
        else:
            scalar_fields[k] = v

    if array_fields:
        # We have at least one array of objects/rows to tabularize
        # Primary array is the first array or largest array
        primary_key, primary_list = max(array_fields, key=lambda item: len(item[1]))

        # Collect columns from items
        item_columns = []
        is_list_of_lists = False
        if primary_list and isinstance(primary_list[0], dict):
            for item in primary_list:
                flat_item = flatten_nested_dict(item)
                for item_k in flat_item.keys():
                    if item_k not in item_columns:
                        item_columns.append(item_k)
        elif primary_list and isinstance(primary_list[0], list):
            is_list_of_lists = True
            max_len = max(len(row) for row in primary_list)
            item_columns = [f"col_{i+1}" for i in range(max_len)]

        # Header columns: Metadata scalars + item columns
        scalar_keys = list(scalar_fields.keys())
        headers = scalar_keys + item_columns
        writer.writerow(headers)

        # Data rows
        if not is_list_of_lists:
            for item in primary_list:
                flat_item = flatten_nested_dict(item)
                row = []
                # Add scalar values
                for sk in scalar_keys:
                    val = scalar_fields.get(sk, "")
                    row.append(val if val is not None else "")
                # Add item values
                for ik in item_columns:
                    val = flat_item.get(ik, "")
                    row.append(val if val is not None else "")
                writer.writerow(row)
        else:
            for row_list in primary_list:
                row = []
                for sk in scalar_keys:
                    val = scalar_fields.get(sk, "")
                    row.append(val if val is not None else "")
                for idx in range(len(item_columns)):
                    val = row_list[idx] if idx < len(row_list) else ""
                    row.append(val if val is not None else "")
                writer.writerow(row)

    else:
        # Flat Key-Value format
        writer.writerow(["Field", "Value"])
        for k, v in flat.items():
            if isinstance(v, list):
                val_str = json.dumps(v, ensure_ascii=False)
            elif v is None:
                val_str = ""
            else:
                val_str = str(v)
            writer.writerow([k, val_str])

    return output.getvalue()


def export_to_txt(
    raw_text: str,
    filename: str = "document",
    document_type: str = "unknown",
    confidence: str = "HIGH",
) -> str:
    """Formats raw text extraction with clean document metadata header."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        "============================================================\n"
        "NOBETH UNIVERSAL OCR - RAW EXTRACTION EXPORT\n"
        "============================================================\n"
        f"Source File   : {filename}\n"
        f"Document Type : {document_type}\n"
        f"Confidence    : {confidence}\n"
        f"Exported At   : {timestamp}\n"
        "============================================================\n\n"
    )
    return header + raw_text


def create_export_bundle(
    structured_data: Dict[str, Any],
    raw_text: str,
    base_filename: str,
    document_type: str = "unknown",
    confidence: str = "HIGH",
) -> ExportBundle:
    """Generates all export formats into an ExportBundle."""
    json_str = export_to_json(structured_data)
    csv_str = export_to_csv(structured_data)
    txt_str = export_to_txt(
        raw_text=raw_text,
        filename=base_filename,
        document_type=document_type,
        confidence=confidence,
    )

    clean_base = base_filename.rsplit(".", 1)[0] if "." in base_filename else base_filename

    return ExportBundle(
        base_filename=clean_base,
        json_content=json_str,
        csv_content=csv_str,
        txt_content=txt_str,
    )
