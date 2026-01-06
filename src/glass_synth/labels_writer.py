"""Write ground-truth labels to JSONL files."""

import json
from pathlib import Path
from typing import List, Dict, Any

from .pdf_renderer import RenderedTable, RenderedRow, RenderedCell
from .table_templates import TableType, LayoutType, RowType, SemanticType
from .non_table_regions import NonTableRegion, non_table_to_model1_label


def table_to_model1_label(table: RenderedTable) -> Dict[str, Any]:
    """
    Convert RenderedTable to Model 1 (table-region classifier) label.

    Model 1 classifies regions as TABLE or NON_TABLE.
    """
    return {
        "table_id": table.table_id,
        "doc_id": table.doc_id,
        "page_index": table.page_index,
        "bbox": list(table.bbox),
        "table_type": table.table_type.value,
        "layout_type": table.layout_type.value,
        "is_table_region": table.is_table_region,
        "vendor_system": table.vendor_system,
        "title_text": table.title_text,
        "fund": table.fund,
        "n_rows": table.n_rows,
        "n_cols": table.n_cols,
        "column_headers": table.column_headers,
        "orientation": table.orientation,
    }


def row_to_model2_label(row: RenderedRow, table: RenderedTable) -> Dict[str, Any]:
    """
    Convert RenderedRow to Model 2 (row-type classifier) label.

    Model 2 classifies rows as HEADER, BODY, SUBTOTAL_TOTAL, or NOTE.
    Only applies to cash tables (CASH_OUT, CASH_IN) with valid layouts.
    """
    # Determine if this is a cash table
    is_cash_table = table.table_type in (TableType.CASH_OUT, TableType.CASH_IN)

    return {
        "row_id": row.row_id,
        "table_id": row.table_id,
        "doc_id": table.doc_id,
        "page_index": row.page_index,
        "row_index": row.row_index,
        "bbox": list(row.bbox),
        "row_type": row.row_type.value,
        "is_cash_table": is_cash_table,
        "layout_type": table.layout_type.value,
        "table_type": table.table_type.value,
        "n_cols": table.n_cols,
    }


def cell_to_model3_label(
    cell: RenderedCell,
    row: RenderedRow,
    table: RenderedTable
) -> Dict[str, Any]:
    """
    Convert RenderedCell to Model 3 (token-column classifier) label.

    Model 3 classifies tokens as DATE, VENDOR, ACCOUNT, AMOUNT, or OTHER.
    Only applies to cash tables.
    """
    return {
        "token_id": f"{row.row_id}_tok{cell.col_index}",
        "row_id": row.row_id,
        "table_id": table.table_id,
        "doc_id": table.doc_id,
        "page_index": cell.page_index,
        "row_index": row.row_index,  # Added per Appendix D
        "col_index": cell.col_index,
        "text": cell.text,
        "bbox": list(cell.bbox),
        "semantic_label": cell.semantic_type.value,
        "row_type": cell.row_type.value,
    }


def cell_to_cells_label(
    cell: RenderedCell,
    row: RenderedRow,
    table: RenderedTable
) -> Dict[str, Any]:
    """
    Convert RenderedCell to cells.jsonl format (Appendix D.2).

    This provides full cell-level ground truth for all tables,
    not just cash tables. Useful for debugging and future models.
    """
    return {
        "cell_id": f"{table.table_id}_r{row.row_index}_c{cell.col_index}",
        "table_id": table.table_id,
        "doc_id": table.doc_id,
        "page_index": cell.page_index,
        "row_index": row.row_index,
        "col_index": cell.col_index,
        "col_semantic": cell.semantic_type.value,  # DATE | VENDOR | ACCOUNT | AMOUNT | OTHER
        "row_type": row.row_type.value,
        "bbox": list(cell.bbox),
        "text": cell.text,
        "table_type": table.table_type.value,
        "layout_type": table.layout_type.value,
    }


def write_labels(
    tables: List[RenderedTable],
    out_dir: Path,
    doc_id: str,
    non_table_regions: List[NonTableRegion] = None
) -> Dict[str, int]:
    """
    Write all labels for a set of tables to JSONL files.

    Creates/appends to:
    - model1_regions.jsonl (table-level labels including NON_TABLE)
    - model2_rows.jsonl (row-level labels, cash tables only)
    - model3_tokens.jsonl (token-level labels, cash tables only)
    - cells.jsonl (cell-level ground truth for ALL tables, per Appendix D.2)

    Returns dict with counts of each label type written.
    """
    out_dir = Path(out_dir)
    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    model1_path = labels_dir / "model1_regions.jsonl"
    model2_path = labels_dir / "model2_rows.jsonl"
    model3_path = labels_dir / "model3_tokens.jsonl"
    cells_path = labels_dir / "cells.jsonl"

    counts = {"tables": 0, "non_tables": 0, "rows": 0, "tokens": 0, "cells": 0}

    # Open files in append mode
    with open(model1_path, "a") as f1, \
         open(model2_path, "a") as f2, \
         open(model3_path, "a") as f3, \
         open(cells_path, "a") as f_cells:

        for table in tables:
            # Model 1: Table regions - ALL layouts (learns what is/isn't a table)
            label1 = table_to_model1_label(table)
            f1.write(json.dumps(label1) + "\n")
            counts["tables"] += 1

            # Per Appendix C: Models 2-3 only train on HORIZONTAL_LEDGER + SPLIT_LEDGER
            # Other layouts (VERTICAL_KV, MATRIX, RAGGED) are detector-only
            is_cash = table.table_type in (TableType.CASH_OUT, TableType.CASH_IN)
            is_valid_layout = table.layout_type in (
                LayoutType.HORIZONTAL_LEDGER,
                LayoutType.SPLIT_LEDGER
            )

            for row in table.rows:
                if is_cash and is_valid_layout:
                    # Model 2: Row types
                    label2 = row_to_model2_label(row, table)
                    f2.write(json.dumps(label2) + "\n")
                    counts["rows"] += 1

                    # Model 3: Token types
                    for cell in row.cells:
                        if cell.text:  # Skip empty cells
                            label3 = cell_to_model3_label(cell, row, table)
                            f3.write(json.dumps(label3) + "\n")
                            counts["tokens"] += 1

                # Cells.jsonl: Write ALL cells from ALL tables (per Appendix D.2)
                for cell in row.cells:
                    if cell.text:  # Skip empty cells
                        cell_label = cell_to_cells_label(cell, row, table)
                        f_cells.write(json.dumps(cell_label) + "\n")
                        counts["cells"] += 1

        # Write NON_TABLE regions for Model 1
        if non_table_regions:
            for region in non_table_regions:
                label1 = non_table_to_model1_label(region)
                f1.write(json.dumps(label1) + "\n")
                counts["non_tables"] += 1

    return counts


def write_document_metadata(
    doc_id: str,
    vendor_system: str,
    property_type: str,
    gl_mask: str,
    degradation_level: int,
    pdf_path: Path,
    period_start: str,
    period_end: str,
    out_dir: Path
) -> None:
    """Write document-level metadata to documents.jsonl."""
    labels_dir = Path(out_dir) / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "doc_id": doc_id,
        "vendor_system": vendor_system,
        "property_type": property_type,
        "fiscal_period_start": period_start,
        "fiscal_period_end": period_end,
        "gl_mask": gl_mask,
        "degradation_level": degradation_level,
        "pdf_path": str(pdf_path),
    }

    docs_path = labels_dir / "documents.jsonl"
    with open(docs_path, "a") as f:
        f.write(json.dumps(metadata) + "\n")


def clear_labels(out_dir: Path) -> None:
    """Clear all existing label files (for fresh generation)."""
    labels_dir = Path(out_dir) / "labels"
    if labels_dir.exists():
        for path in labels_dir.glob("*.jsonl"):
            path.unlink()
