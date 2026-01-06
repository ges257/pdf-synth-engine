"""Write ground-truth labels to JSONL files."""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from .pdf_renderer import RenderedTable, RenderedRow, RenderedCell
from .table_templates import TableType, LayoutType, RowType, SemanticType
from .non_table_regions import NonTableRegion, non_table_to_model1_label

# Page dimensions for coordinate conversion (landscape letter)
DEFAULT_PAGE_WIDTH = 792.0
DEFAULT_PAGE_HEIGHT = 612.0
MIN_BBOX_WIDTH = 10.0
MIN_BBOX_HEIGHT = 5.0


# ============================================================================
# COORDINATE CONVERSION UTILITIES
# ============================================================================

def to_pdfplumber_bbox(
    bbox_rl: Tuple[float, float, float, float],
    page_height: float
) -> Tuple[float, float, float, float]:
    """
    Convert ReportLab bbox to pdfplumber coordinates.

    ReportLab: origin at BOTTOM-LEFT, y increases UPWARD
               bbox = [x0, y0, x1, y1] where y0 is bottom, y1 is top

    pdfplumber: origin at TOP-LEFT, y increases DOWNWARD
                bbox = [x0, top, x1, bottom] where top < bottom

    Args:
        bbox_rl: ReportLab bbox [x0, y_bottom, x1, y_top]
        page_height: Page height in points

    Returns:
        pdfplumber bbox [x0, top, x1, bottom]
    """
    x0, y0, x1, y1 = bbox_rl
    # In ReportLab: y0 is bottom, y1 is top (y0 < y1)
    # Convert to pdfplumber: top = H - y1, bottom = H - y0
    top = page_height - y1
    bottom = page_height - y0
    return (x0, top, x1, bottom)


def clamp_bbox_rl(
    bbox: Tuple[float, float, float, float],
    page_width: float,
    page_height: float
) -> Optional[Tuple[float, float, float, float]]:
    """
    Clamp ReportLab bbox to page bounds.

    Returns None if bbox becomes invalid (collapsed or too small).
    """
    x0, y0, x1, y1 = bbox

    # Clamp to page bounds
    x0 = max(0, min(x0, page_width))
    x1 = max(0, min(x1, page_width))
    y0 = max(0, min(y0, page_height))
    y1 = max(0, min(y1, page_height))

    # Check if collapsed
    if x1 <= x0 or y1 <= y0:
        return None

    # Check minimum size
    if (x1 - x0) < MIN_BBOX_WIDTH or (y1 - y0) < MIN_BBOX_HEIGHT:
        return None

    return (x0, y0, x1, y1)


def clamp_bbox_pl(
    bbox: Tuple[float, float, float, float],
    page_width: float,
    page_height: float
) -> Optional[Tuple[float, float, float, float]]:
    """
    Clamp pdfplumber bbox to page bounds.

    pdfplumber format: [x0, top, x1, bottom] where top < bottom

    Returns None if bbox becomes invalid.
    """
    x0, top, x1, bottom = bbox

    # Clamp to page bounds
    x0 = max(0, min(x0, page_width))
    x1 = max(0, min(x1, page_width))
    top = max(0, min(top, page_height))
    bottom = max(0, min(bottom, page_height))

    # Check if collapsed (top should be < bottom in pdfplumber coords)
    if x1 <= x0 or bottom <= top:
        return None

    # Check minimum size
    if (x1 - x0) < MIN_BBOX_WIDTH or (bottom - top) < MIN_BBOX_HEIGHT:
        return None

    return (x0, top, x1, bottom)


def convert_and_validate_bbox(
    bbox_rl: Tuple[float, float, float, float],
    page_width: float,
    page_height: float
) -> Tuple[Optional[List[float]], str]:
    """
    Convert ReportLab bbox to pdfplumber and validate.

    Args:
        bbox_rl: ReportLab bbox
        page_width: Page width
        page_height: Page height

    Returns:
        (bbox_pl, status) where status is:
        - "OK": bbox valid without clamping
        - "CLAMPED": bbox required clamping
        - "DROPPED": bbox invalid, should be dropped
    """
    # Step 1: Clamp in ReportLab coords
    clamped_rl = clamp_bbox_rl(bbox_rl, page_width, page_height)
    if clamped_rl is None:
        return None, "DROPPED"

    was_clamped_rl = (clamped_rl != bbox_rl)

    # Step 2: Convert to pdfplumber
    bbox_pl = to_pdfplumber_bbox(clamped_rl, page_height)

    # Step 3: Clamp in pdfplumber coords (safety net)
    clamped_pl = clamp_bbox_pl(bbox_pl, page_width, page_height)
    if clamped_pl is None:
        return None, "DROPPED"

    was_clamped_pl = (clamped_pl != bbox_pl)

    status = "CLAMPED" if (was_clamped_rl or was_clamped_pl) else "OK"
    return list(clamped_pl), status


def compute_table_bbox_from_cells(
    valid_cell_bboxes: List[List[float]],
    page_width: float,
    page_height: float
) -> Optional[List[float]]:
    """
    Compute table bbox as union of valid cell bboxes.

    Args:
        valid_cell_bboxes: List of pdfplumber bboxes [x0, top, x1, bottom]
        page_width: Page width
        page_height: Page height

    Returns:
        Union bbox clamped to page bounds, or None if no valid cells
    """
    if not valid_cell_bboxes:
        return None

    x0 = min(b[0] for b in valid_cell_bboxes)
    top = min(b[1] for b in valid_cell_bboxes)
    x1 = max(b[2] for b in valid_cell_bboxes)
    bottom = max(b[3] for b in valid_cell_bboxes)

    # Clamp union to page bounds
    x0 = max(0, min(x0, page_width))
    x1 = max(0, min(x1, page_width))
    top = max(0, min(top, page_height))
    bottom = max(0, min(bottom, page_height))

    if x1 <= x0 or bottom <= top:
        return None

    return [x0, top, x1, bottom]


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
    non_table_regions: List[NonTableRegion] = None,
    page_width: float = DEFAULT_PAGE_WIDTH,
    page_height: float = DEFAULT_PAGE_HEIGHT
) -> Dict[str, int]:
    """
    Write all labels for a set of tables to JSONL files.

    All bboxes are converted from ReportLab coords to pdfplumber coords.
    Invalid bboxes (outside page bounds) are dropped.

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

    counts = {
        "tables": 0,
        "non_tables": 0,
        "rows": 0,
        "tokens": 0,
        "cells": 0,
        "cells_dropped": 0,
        "cells_clamped": 0,
        "rows_dropped": 0,
    }

    # Open files in append mode
    with open(model1_path, "a") as f1, \
         open(model2_path, "a") as f2, \
         open(model3_path, "a") as f3, \
         open(cells_path, "a") as f_cells:

        for table in tables:
            # Collect valid cell bboxes for computing table_bbox
            valid_cell_bboxes = []

            # Per Appendix C: Models 2-3 only train on HORIZONTAL_LEDGER + SPLIT_LEDGER
            is_cash = table.table_type in (TableType.CASH_OUT, TableType.CASH_IN)
            is_valid_layout = table.layout_type in (
                LayoutType.HORIZONTAL_LEDGER,
                LayoutType.SPLIT_LEDGER
            )

            for row in table.rows:
                # Convert and validate row bbox
                row_bbox_pl, row_status = convert_and_validate_bbox(
                    row.bbox, page_width, page_height
                )

                if row_status == "DROPPED":
                    counts["rows_dropped"] += 1
                    continue  # Skip entire row if bbox invalid

                if is_cash and is_valid_layout:
                    # Model 2: Row types (with converted bbox)
                    label2 = row_to_model2_label(row, table)
                    label2["bbox"] = row_bbox_pl
                    f2.write(json.dumps(label2) + "\n")
                    counts["rows"] += 1

                # Process cells in this row
                for cell in row.cells:
                    if not cell.text:  # Skip empty cells
                        continue

                    # Convert and validate cell bbox
                    cell_bbox_pl, cell_status = convert_and_validate_bbox(
                        cell.bbox, page_width, page_height
                    )

                    if cell_status == "DROPPED":
                        counts["cells_dropped"] += 1
                        continue

                    if cell_status == "CLAMPED":
                        counts["cells_clamped"] += 1

                    # Track valid cell bbox for table_bbox computation
                    # Only include non-TEMPLATE rows in table_bbox
                    if row.row_type != RowType.TEMPLATE:
                        valid_cell_bboxes.append(cell_bbox_pl)

                    # Model 3: Token types (cash tables only)
                    if is_cash and is_valid_layout:
                        label3 = cell_to_model3_label(cell, row, table)
                        label3["bbox"] = cell_bbox_pl
                        f3.write(json.dumps(label3) + "\n")
                        counts["tokens"] += 1

                    # Cells.jsonl: Write ALL cells from ALL tables
                    cell_label = cell_to_cells_label(cell, row, table)
                    cell_label["bbox"] = cell_bbox_pl
                    f_cells.write(json.dumps(cell_label) + "\n")
                    counts["cells"] += 1

            # Compute table_bbox from valid (non-TEMPLATE) cell bboxes
            computed_table_bbox = compute_table_bbox_from_cells(
                valid_cell_bboxes, page_width, page_height
            )

            if computed_table_bbox is None:
                # No valid cells - skip this table entirely
                continue

            # Model 1: Table regions with computed bbox
            label1 = table_to_model1_label(table)
            label1["bbox"] = computed_table_bbox
            f1.write(json.dumps(label1) + "\n")
            counts["tables"] += 1

        # Write NON_TABLE regions for Model 1 (also convert bbox)
        if non_table_regions:
            for region in non_table_regions:
                label1 = non_table_to_model1_label(region)
                # Convert non-table region bbox
                if "bbox" in label1 and label1["bbox"]:
                    region_bbox_pl, status = convert_and_validate_bbox(
                        tuple(label1["bbox"]), page_width, page_height
                    )
                    if region_bbox_pl:
                        label1["bbox"] = region_bbox_pl
                        f1.write(json.dumps(label1) + "\n")
                        counts["non_tables"] += 1
                else:
                    f1.write(json.dumps(label1) + "\n")
                    counts["non_tables"] += 1

    # Log statistics
    if counts["cells_dropped"] > 0 or counts["cells_clamped"] > 0:
        print(f"  [{doc_id}] Cells: {counts['cells']} written, "
              f"{counts['cells_dropped']} dropped, {counts['cells_clamped']} clamped")

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


# ============================================================================
# MODEL 5: Token→Grid Reassembler Ground Truth
# ============================================================================

def cell_to_model5_gt(
    cell: RenderedCell,
    row: RenderedRow,
    table: RenderedTable
) -> Dict[str, Any]:
    """
    Convert RenderedCell to Model 5 synthetic_gt_cells.jsonl format.

    Model 5 uses col_id (string) instead of col_index (int) for column identity.
    Format matches Appendix A.3 of the Model 5 spec.
    """
    return {
        "table_id": table.table_id,
        "row_id": row.row_index,
        "col_id": f"COL_{cell.col_index}",
        "col_name": cell.semantic_type.value,  # Semantic role as col_name
        "text": cell.text,
        "bbox": list(cell.bbox),
    }


def table_to_manifest(table: RenderedTable, pdf_path: str) -> Dict[str, Any]:
    """
    Convert RenderedTable to tables_manifest.jsonl format.

    One record per table instance for Model 5 processing.
    Format matches Appendix A.2 of the Model 5 spec.
    """
    return {
        "doc_id": table.doc_id,
        "table_id": table.table_id,
        "pdf_path": pdf_path,
        "page_num": table.page_index,
        "table_bbox": list(table.bbox),
        "gt_ref": {
            "cells_jsonl": "synthetic_gt_cells.jsonl",
        },
        "notes": {
            "template_family": table.vendor_system,
            "table_type": table.table_type.value,
            "layout_type": table.layout_type.value,
            "n_rows": table.n_rows,
            "n_cols": table.n_cols,
        }
    }


def write_model5_labels(
    tables: List[RenderedTable],
    out_dir: Path,
    doc_id: str,
    pdf_path: str,
    page_width: float = DEFAULT_PAGE_WIDTH,
    page_height: float = DEFAULT_PAGE_HEIGHT
) -> Dict[str, int]:
    """
    Write Model 5 specific ground truth files.

    All bboxes are converted from ReportLab coords to pdfplumber coords.

    Creates/appends to:
    - synthetic_gt_cells.jsonl (cell-level GT with col_id)
    - tables_manifest.jsonl (table-level manifest)

    Returns dict with counts.
    """
    out_dir = Path(out_dir)
    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    gt_cells_path = labels_dir / "synthetic_gt_cells.jsonl"
    manifest_path = labels_dir / "tables_manifest.jsonl"

    counts = {"model5_cells": 0, "model5_tables": 0, "model5_cells_dropped": 0}

    with open(gt_cells_path, "a") as f_cells, \
         open(manifest_path, "a") as f_manifest:

        for table in tables:
            # Collect valid cell bboxes for computing table_bbox
            valid_cell_bboxes = []

            # Write cell-level GT
            for row in table.rows:
                # Skip TEMPLATE rows for Model 5 (they're design chrome, not data)
                if row.row_type == RowType.TEMPLATE:
                    continue

                for cell in row.cells:
                    if not cell.text:  # Skip empty cells
                        continue

                    # Convert and validate cell bbox
                    cell_bbox_pl, status = convert_and_validate_bbox(
                        cell.bbox, page_width, page_height
                    )

                    if status == "DROPPED":
                        counts["model5_cells_dropped"] += 1
                        continue

                    valid_cell_bboxes.append(cell_bbox_pl)

                    cell_gt = cell_to_model5_gt(cell, row, table)
                    cell_gt["bbox"] = cell_bbox_pl
                    f_cells.write(json.dumps(cell_gt) + "\n")
                    counts["model5_cells"] += 1

            # Compute table_bbox from valid cells
            computed_table_bbox = compute_table_bbox_from_cells(
                valid_cell_bboxes, page_width, page_height
            )

            if computed_table_bbox is None:
                continue  # Skip table with no valid cells

            # Write table manifest entry with computed bbox
            manifest_entry = table_to_manifest(table, pdf_path)
            manifest_entry["table_bbox"] = computed_table_bbox
            f_manifest.write(json.dumps(manifest_entry) + "\n")
            counts["model5_tables"] += 1

    return counts
