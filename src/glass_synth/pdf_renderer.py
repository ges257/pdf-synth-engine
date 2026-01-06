"""PDF rendering using ReportLab."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from datetime import date

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.colors import black, gray, lightgrey, white, Color
from reportlab.pdfgen import canvas

# Default cell padding (used as fallback; vendor styles override this)
CELL_PADDING = 3

from .table_templates import (
    TableTemplate, TableType, SemanticType, RowType, LayoutType,
    get_template, select_column_synonyms
)
from .layout_engine import (
    LayoutEngine, PageLayout, TablePlacement,
    RowPlacement, CellPlacement, PORTRAIT_SIZE, LANDSCAPE_SIZE
)
from .ledger_generator import CashTransaction
from .vendor_styles import (
    VendorStyle, GridStyle, get_vendor_style, get_bold_font, VENDOR_STYLES
)
from .non_table_regions import NonTableGenerator, NonTableRegion
from .degradation import DegradationEngine, get_degradation_engine


@dataclass
class RenderedCell:
    """Metadata for a rendered cell."""
    text: str
    page_index: int
    row_index: int
    col_index: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    semantic_type: SemanticType
    row_type: RowType


@dataclass
class RenderedRow:
    """Metadata for a rendered row."""
    row_id: str
    table_id: str
    page_index: int
    row_index: int
    bbox: Tuple[float, float, float, float]
    row_type: RowType
    cells: List[RenderedCell]


@dataclass
class RenderedTable:
    """Metadata for a rendered table."""
    table_id: str
    doc_id: str
    page_index: int
    bbox: Tuple[float, float, float, float]
    table_type: TableType
    layout_type: LayoutType
    is_table_region: bool
    vendor_system: str
    title_text: str
    fund: str
    n_rows: int
    n_cols: int
    column_headers: List[str]
    rows: List[RenderedRow]
    orientation: str = "portrait"


def truncate_text(text: str, max_width: float, font_name: str, font_size: int, canvas_obj: canvas.Canvas) -> str:
    """Truncate text to fit within max_width, adding '...' if needed."""
    if not text:
        return text

    text_width = canvas_obj.stringWidth(text, font_name, font_size)
    if text_width <= max_width:
        return text

    # Binary search for the right length
    ellipsis = "..."
    ellipsis_width = canvas_obj.stringWidth(ellipsis, font_name, font_size)
    available_width = max_width - ellipsis_width

    if available_width <= 0:
        return ellipsis[:1]  # Just return "." if no room

    # Start from full text and reduce
    for i in range(len(text), 0, -1):
        truncated = text[:i]
        if canvas_obj.stringWidth(truncated, font_name, font_size) <= available_width:
            return truncated + ellipsis

    return ellipsis


class PDFRenderer:
    """Renders tables to PDF and captures metadata for labels."""

    def __init__(self, layout: Optional[PageLayout] = None):
        self.layout = layout or PageLayout()
        self.layout_engine = LayoutEngine(self.layout)
        self._vendor_style: Optional[VendorStyle] = None
        self._row_counter: int = 0  # Track row for alternating row colors
        self._degradation: Optional[DegradationEngine] = None

    @property
    def vendor_style(self) -> VendorStyle:
        """Get the current vendor style."""
        if self._vendor_style is None:
            return get_vendor_style("AKAM_NEW")  # Default
        return self._vendor_style

    @property
    def cell_padding(self) -> float:
        """Get cell padding from vendor style, with degradation applied."""
        base_padding = self.vendor_style.cell_padding
        if self._degradation:
            return self._degradation.apply_padding_variation(base_padding)
        return base_padding

    @property
    def degradation(self) -> Optional[DegradationEngine]:
        """Get the current degradation engine."""
        return self._degradation

    def render_document(
        self,
        doc_id: str,
        pdf_path: Path,
        tables_data: List[Tuple[TableTemplate, str, List[CashTransaction], LayoutType]],
        vendor_system: str,
        rng,
        orientation: str = "portrait",
        include_non_table_regions: bool = True,
        degradation_level: int = 3,
    ) -> Tuple[List[RenderedTable], List[NonTableRegion], int]:
        """
        Render a complete document with multiple tables.

        Args:
            doc_id: Document identifier
            pdf_path: Output PDF path
            tables_data: List of (template, title, transactions, layout_type) tuples
            vendor_system: Vendor system name
            rng: Random number generator
            orientation: "portrait" or "landscape"
            include_non_table_regions: Whether to generate NON_TABLE regions
            degradation_level: 1-5, where 1 is clean and 5 is heavily degraded

        Returns:
            Tuple of (list of RenderedTable metadata, list of NonTableRegion, total page count)
        """
        # Set vendor style for this document
        self._vendor_style = get_vendor_style(vendor_system)

        # Set degradation engine
        self._degradation = get_degradation_engine(degradation_level, rng)

        # Create canvas with specified orientation
        if orientation == "landscape":
            pagesize = LANDSCAPE_SIZE
            self.layout = PageLayout.landscape()
        else:
            pagesize = PORTRAIT_SIZE
            self.layout = PageLayout.portrait()

        self.layout_engine = LayoutEngine(self.layout)
        c = canvas.Canvas(str(pdf_path), pagesize=pagesize)

        self.layout_engine.reset()
        rendered_tables: List[RenderedTable] = []
        non_table_regions: List[NonTableRegion] = []
        self._current_canvas_page = 0  # Track which page the canvas is on
        self._orientation = orientation
        self._page_has_content = False  # Track if current page has content drawn
        self._row_counter = 0  # Reset row counter for alternating rows

        # Initialize non-table generator
        non_table_gen = NonTableGenerator()

        # Generate document header on first page (with some probability)
        if include_non_table_regions and rng.random() > 0.3:
            header_region, new_y = non_table_gen.generate_document_header(
                c=c,
                doc_id=doc_id,
                page_index=0,
                style=self.vendor_style,
                start_x=self.layout.content_start_x,
                start_y=self.layout_engine.current_y,
                width=self.layout.content_width,
                rng=rng,
            )
            non_table_regions.append(header_region)
            self.layout_engine.current_y = new_y
            self._page_has_content = True

        # Process tables, handling split layouts specially
        table_idx = 0
        section_idx = 0
        i = 0
        while i < len(tables_data):
            template, title, transactions, layout_type = tables_data[i]

            if layout_type == LayoutType.SPLIT_LEDGER and i + 1 < len(tables_data):
                # Render two tables side by side
                left_table = self._render_table(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template,
                    title=title,
                    transactions=transactions,
                    vendor_system=vendor_system,
                    rng=rng,
                    layout_type=layout_type,
                    is_split_right=False,
                )
                rendered_tables.append(left_table)

                # Get next table for right panel
                i += 1
                table_idx += 1
                template2, title2, transactions2, _ = tables_data[i]
                right_table = self._render_table(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template2,
                    title=title2,
                    transactions=transactions2,
                    vendor_system=vendor_system,
                    rng=rng,
                    layout_type=layout_type,
                    is_split_right=True,
                )
                rendered_tables.append(right_table)
            elif layout_type == LayoutType.VERTICAL_KV:
                # Render vertical key-value form
                rendered_table = self._render_vertical_kv(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template,
                    title=title,
                    transactions=transactions,
                    vendor_system=vendor_system,
                    rng=rng,
                )
                rendered_tables.append(rendered_table)
            elif layout_type == LayoutType.MATRIX:
                # Render matrix/cross-tab table
                rendered_table = self._render_matrix(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template,
                    title=title,
                    data=transactions,
                    vendor_system=vendor_system,
                    rng=rng,
                )
                rendered_tables.append(rendered_table)
            elif layout_type == LayoutType.RAGGED:
                # Render ragged/pseudo-table
                rendered_table = self._render_ragged(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template,
                    title=title,
                    transactions=transactions,
                    vendor_system=vendor_system,
                    rng=rng,
                )
                rendered_tables.append(rendered_table)
            else:
                # Standard horizontal ledger
                rendered_table = self._render_table(
                    c=c,
                    doc_id=doc_id,
                    table_idx=table_idx,
                    template=template,
                    title=title,
                    transactions=transactions,
                    vendor_system=vendor_system,
                    rng=rng,
                    layout_type=layout_type,
                )
                rendered_tables.append(rendered_table)

            # Add section header or note between tables sometimes
            if include_non_table_regions and i < len(tables_data) - 1 and rng.random() > 0.6:
                if rng.random() > 0.5:
                    # Section header
                    section_region, new_y = non_table_gen.generate_section_header(
                        c=c,
                        doc_id=doc_id,
                        page_index=self.layout_engine.current_page,
                        section_idx=section_idx,
                        style=self.vendor_style,
                        start_x=self.layout.content_start_x,
                        start_y=self.layout_engine.current_y - 15,
                        width=self.layout.content_width,
                        rng=rng,
                    )
                    non_table_regions.append(section_region)
                    self.layout_engine.current_y = new_y
                    section_idx += 1
                else:
                    # Note block
                    note_region, new_y = non_table_gen.generate_note_block(
                        c=c,
                        doc_id=doc_id,
                        page_index=self.layout_engine.current_page,
                        note_idx=section_idx,
                        style=self.vendor_style,
                        start_x=self.layout.content_start_x,
                        start_y=self.layout_engine.current_y - 15,
                        width=self.layout.content_width,
                        rng=rng,
                    )
                    non_table_regions.append(note_region)
                    self.layout_engine.current_y = new_y
                    section_idx += 1

            i += 1
            table_idx += 1

        # Add footer or signature at end of document sometimes
        if include_non_table_regions and rng.random() > 0.5:
            if rng.random() > 0.7:
                # Signature block
                sig_region, new_y = non_table_gen.generate_signature_block(
                    c=c,
                    doc_id=doc_id,
                    page_index=self.layout_engine.current_page,
                    style=self.vendor_style,
                    start_x=self.layout.content_start_x,
                    start_y=self.layout_engine.current_y - 20,
                    width=self.layout.content_width,
                    rng=rng,
                )
                non_table_regions.append(sig_region)
            else:
                # Footer/note
                footer_region = non_table_gen.generate_page_footer(
                    c=c,
                    doc_id=doc_id,
                    page_index=self.layout_engine.current_page,
                    page_number=self.layout_engine.current_page + 1,
                    total_pages=self.layout_engine.current_page + 1,
                    style=self.vendor_style,
                    start_x=self.layout.content_start_x,
                    bottom_y=self.layout.margin_bottom,
                    width=self.layout.content_width,
                    rng=rng,
                )
                non_table_regions.append(footer_region)

        # Finalize PDF
        c.save()

        total_pages = self.layout_engine.current_page + 1
        return rendered_tables, non_table_regions, total_pages

    def _render_table(
        self,
        c: canvas.Canvas,
        doc_id: str,
        table_idx: int,
        template: TableTemplate,
        title: str,
        transactions: List[CashTransaction],
        vendor_system: str,
        rng,
        layout_type: LayoutType = LayoutType.HORIZONTAL_LEDGER,
        is_split_right: bool = False,
    ) -> RenderedTable:
        """Render a single table and return metadata."""

        # Select column headers with synonyms
        column_headers = select_column_synonyms(template.column_specs, rng)

        # Prepare row data (with row types for NOTE rows)
        header_row = column_headers
        data_rows, data_row_types = self._prepare_data_rows(template, transactions, rng)

        num_data_rows = len(data_rows)

        # Get table placement (this may trigger a page break in layout engine)
        placement = self.layout_engine.place_table(
            template=template,
            num_data_rows=num_data_rows,
            title=title,
            table_index=table_idx,
            layout_type=layout_type,
            is_split_right=is_split_right,
        )

        # Sync canvas page with layout engine page
        while self._current_canvas_page < placement.page_index:
            # Only call showPage() if we've drawn content to the current page
            # This prevents blank pages when a large table can't fit on page 0
            if self._page_has_content:
                c.showPage()
            self._current_canvas_page += 1
            self._page_has_content = False

        table_id = f"{doc_id}__p{placement.page_index}_t{table_idx}"

        # Compute positions
        row_positions = self.layout_engine.compute_row_positions(
            placement, num_data_rows
        )

        # Combine header + data for cell position calculation
        all_row_data = [header_row] + data_rows

        cell_positions = self.layout_engine.compute_cell_positions(
            placement, row_positions, all_row_data
        )

        # Render title
        self._draw_title(c, placement, title, template)

        # Render header row
        header_cells = [cp for cp in cell_positions if cp.row_index == 0]
        self._draw_header_row(c, header_cells, template)

        # Render data rows
        for row_idx in range(1, len(all_row_data)):
            row_cells = [cp for cp in cell_positions if cp.row_index == row_idx]
            is_subtotal = self._is_subtotal_row(data_rows[row_idx - 1])
            self._draw_data_row(c, row_cells, template, is_subtotal, row_index=row_idx)

        # Draw grid lines if enabled
        if template.has_grid_lines:
            self._draw_grid_lines(c, placement, row_positions, template)

        # Mark that we've drawn content to this page
        self._page_has_content = True

        # Build metadata
        rendered_rows: List[RenderedRow] = []

        # Prepend HEADER to data_row_types to get full row_types list
        all_row_types = [RowType.HEADER] + data_row_types

        for row_idx, row_pos in enumerate(row_positions):
            row_id = f"{table_id}_r{row_idx}"

            # Use row type from _prepare_data_rows (HEADER for idx 0, then data_row_types)
            row_type = all_row_types[row_idx] if row_idx < len(all_row_types) else RowType.BODY

            row_cells = [cp for cp in cell_positions if cp.row_index == row_idx]
            row_texts = all_row_data[row_idx]

            rendered_cells: List[RenderedCell] = []
            for col_idx, (cell_pos, text) in enumerate(zip(row_cells, row_texts)):
                bbox = self.layout_engine.get_cell_bbox(cell_pos)
                semantic_type = template.column_specs[col_idx].semantic_type

                rendered_cells.append(RenderedCell(
                    text=text,
                    page_index=placement.page_index,
                    row_index=row_idx,
                    col_index=col_idx,
                    bbox=bbox,
                    semantic_type=semantic_type,
                    row_type=row_type,
                ))

            row_bbox = self.layout_engine.get_row_bbox(placement, row_pos)
            rendered_rows.append(RenderedRow(
                row_id=row_id,
                table_id=table_id,
                page_index=placement.page_index,
                row_index=row_idx,
                bbox=row_bbox,
                row_type=row_type,
                cells=rendered_cells,
            ))

        table_bbox = self.layout_engine.get_table_bbox(placement)

        return RenderedTable(
            table_id=table_id,
            doc_id=doc_id,
            page_index=placement.page_index,
            bbox=table_bbox,
            table_type=template.table_type,
            layout_type=layout_type,
            is_table_region=True,
            vendor_system=vendor_system,
            title_text=title,
            fund="OPERATING",
            n_rows=len(rendered_rows),
            n_cols=len(template.column_specs),
            column_headers=column_headers,
            rows=rendered_rows,
            orientation=getattr(self, '_orientation', 'portrait'),
        )

    def _prepare_data_rows(
        self,
        template: TableTemplate,
        data: Any,
        rng=None
    ) -> Tuple[List[List[str]], List[RowType]]:
        """Convert data to row data strings.

        Handles both CashTransaction objects and dict data for non-cash tables.

        Returns:
            Tuple of (rows, row_types) where row_types contains RowType for each row
        """
        # Check if data contains CashTransaction objects or dicts
        if not data:
            return [], []

        if isinstance(data[0], CashTransaction):
            return self._prepare_cash_rows(template, data, rng)
        else:
            # For dict data, all rows are BODY except last which is SUBTOTAL if supported
            rows = self._prepare_dict_rows(template, data)
            row_types = [RowType.BODY] * len(rows)
            if template.supports_subtotals and rows:
                row_types[-1] = RowType.SUBTOTAL_TOTAL
            return rows, row_types

    def _prepare_cash_rows(
        self,
        template: TableTemplate,
        transactions: List[CashTransaction],
        rng=None
    ) -> Tuple[List[List[str]], List[RowType]]:
        """
        Convert CashTransaction objects to row data strings.

        Returns:
            Tuple of (rows, row_types) where row_types contains RowType for each row
            (BODY, NOTE, or SUBTOTAL_TOTAL - HEADER is added separately)
        """
        from .ledger_generator import generate_note_content

        rows = []
        row_types = []
        running_balance = 0.0
        opening_balance = 0.0

        for txn in transactions:
            running_balance += txn.amount
            if txn.opening_balance is not None:
                opening_balance = txn.opening_balance

            row = []
            for spec in template.column_specs:
                # DATE columns
                if spec.semantic_type == SemanticType.DATE:
                    if "Invoice" in spec.name and txn.invoice_date:
                        row.append(txn.invoice_date.strftime("%m/%d/%y"))
                    elif "Check" in spec.name and txn.check_date:
                        row.append(txn.check_date.strftime("%m/%d/%y"))
                    else:
                        row.append(txn.date.strftime("%m/%d/%y"))

                # VENDOR columns
                elif spec.semantic_type == SemanticType.VENDOR:
                    if "Unit" in spec.name:
                        row.append(txn.unit_id or "")
                    elif "Owner" in spec.name or "Resident" in spec.name:
                        row.append(txn.vendor)
                    else:
                        row.append(txn.vendor)

                # VENDOR_CODE columns
                elif spec.semantic_type == SemanticType.VENDOR_CODE:
                    row.append(txn.vendor_code or "")

                # UNIT_CODE columns
                elif spec.semantic_type == SemanticType.UNIT_CODE:
                    if "Acct" in spec.name or "Account" in spec.name:
                        row.append(txn.account_code or "")
                    else:
                        row.append(txn.unit_id or "")

                # ACCOUNT columns
                elif spec.semantic_type == SemanticType.ACCOUNT:
                    row.append(txn.gl_code)

                # AMOUNT columns
                elif spec.semantic_type == SemanticType.AMOUNT:
                    if "Base" in spec.name and txn.base_charge is not None:
                        row.append(f"{txn.base_charge:,.2f}")
                    elif "Shares" in spec.name and txn.shares is not None:
                        row.append(str(txn.shares))
                    elif "Paid" in spec.name:
                        row.append(f"{txn.amount:,.2f}")
                    else:
                        row.append(f"{txn.amount:,.2f}")

                # BALANCE columns
                elif spec.semantic_type == SemanticType.BALANCE:
                    if "Open" in spec.name and txn.opening_balance is not None:
                        row.append(f"{txn.opening_balance:,.2f}")
                    elif "Close" in spec.name or "Balance" in spec.name:
                        closing = (txn.opening_balance or 0) + txn.amount
                        row.append(f"{closing:,.2f}")
                    else:
                        row.append(f"{running_balance:,.2f}")

                # INVOICE_NUMBER columns
                elif spec.semantic_type == SemanticType.INVOICE_NUMBER:
                    row.append(txn.invoice_number or "")

                # CHECK_NUMBER columns
                elif spec.semantic_type == SemanticType.CHECK_NUMBER:
                    row.append(txn.check_number)

                # STATUS columns
                elif spec.semantic_type == SemanticType.STATUS:
                    row.append(txn.status or "")

                # OTHER columns (Description, Remarks, P/O, etc.)
                else:
                    if "Description" in spec.name or "Expense" in spec.name:
                        row.append(txn.description)
                    elif "Remarks" in spec.name or "Notes" in spec.name:
                        row.append(txn.remarks or "")
                    elif "P/O" in spec.name or "P.O." in spec.name:
                        row.append(txn.po_number or "")
                    elif "Charges" in spec.name:
                        row.append(txn.description)
                    else:
                        row.append("")

            rows.append(row)
            row_types.append(RowType.BODY)

            # Insert NOTE row with ~5% probability
            if rng is not None and rng.random() < 0.05:
                note_content = generate_note_content(txn.gl_name, rng)
                if note_content:  # Don't add empty notes
                    note_row = [""] * len(template.column_specs)
                    # Put note text in a wide column (Description or first OTHER column)
                    for idx, spec in enumerate(template.column_specs):
                        if "Description" in spec.name or spec.semantic_type == SemanticType.OTHER:
                            note_row[idx] = note_content
                            break
                    rows.append(note_row)
                    row_types.append(RowType.NOTE)

        # Add subtotal row
        if template.supports_subtotals and len(transactions) > 0:
            total_amount = sum(t.amount for t in transactions)
            subtotal_row = []
            for spec in template.column_specs:
                if spec.semantic_type == SemanticType.AMOUNT:
                    subtotal_row.append(f"{total_amount:,.2f}")
                elif spec.semantic_type == SemanticType.BALANCE:
                    subtotal_row.append(f"{running_balance:,.2f}")
                elif spec.semantic_type == SemanticType.VENDOR:
                    subtotal_row.append("TOTAL")
                else:
                    subtotal_row.append("")
            rows.append(subtotal_row)
            row_types.append(RowType.SUBTOTAL_TOTAL)

        return rows, row_types

    def _prepare_dict_rows(
        self,
        template: TableTemplate,
        data: List[dict]
    ) -> List[List[str]]:
        """Convert dict data to row data strings for non-cash tables."""
        rows = []

        # Map column names to dict keys
        col_to_key = {
            # BUDGET columns
            "Account": "account",
            "Current": "current",
            "YTD Actual": "ytd_actual",
            "YTD Budget": "ytd_budget",
            "Annual Budget": "annual_budget",
            "Variance": "variance",
            # UNPAID columns
            "Date": "date",
            "Vendor": "vendor",
            "Invoice #": "invoice_num",
            "Due Date": "due_date",
            "GL Code": "gl_code",
            "Description": "description",
            "Amount": "amount",
            # AGING columns
            "Unit": "unit",
            "Owner": "owner",
            "30 Days": "days_30",
            "60 Days": "days_60",
            "90 Days": "days_90",
            "90+ Days": "days_90_plus",
            "Total": "total",
            # GL columns
            "Reference": "reference",
            "Debit": "debit",
            "Credit": "credit",
            "Balance": "balance",
        }

        running_total = 0.0

        for item in data:
            row = []
            for spec in template.column_specs:
                key = col_to_key.get(spec.name, spec.name.lower().replace(" ", "_"))
                value = item.get(key, "")

                # Format based on type
                if value is None:
                    row.append("")
                elif isinstance(value, float):
                    if spec.name == "Variance":
                        row.append(f"{value:+,.2f}")  # Show sign for variance
                    else:
                        row.append(f"{value:,.2f}")
                    running_total += value if spec.name in ["Amount", "Total"] else 0
                elif hasattr(value, 'strftime'):  # date object
                    row.append(value.strftime("%m/%d/%y"))
                else:
                    row.append(str(value))
            rows.append(row)

        # Add subtotal row for tables that support it
        if template.supports_subtotals and len(data) > 0:
            subtotal_row = []
            for spec in template.column_specs:
                if spec.semantic_type == SemanticType.AMOUNT:
                    # Calculate total for this column
                    key = col_to_key.get(spec.name, spec.name.lower().replace(" ", "_"))
                    total = sum(item.get(key, 0) or 0 for item in data if isinstance(item.get(key), (int, float)))
                    if spec.name == "Variance":
                        subtotal_row.append(f"{total:+,.2f}")
                    else:
                        subtotal_row.append(f"{total:,.2f}")
                elif spec.semantic_type == SemanticType.ACCOUNT or spec.name == "Account":
                    subtotal_row.append("TOTAL")
                elif spec.semantic_type == SemanticType.VENDOR:
                    subtotal_row.append("TOTAL")
                else:
                    subtotal_row.append("")
            rows.append(subtotal_row)

        return rows

    def _is_subtotal_row(self, row: List[str]) -> bool:
        """Check if a row is a subtotal/total row."""
        return any("TOTAL" in cell.upper() for cell in row if cell)

    def _draw_title(
        self,
        c: canvas.Canvas,
        placement: TablePlacement,
        title: str,
        template: TableTemplate
    ):
        """Draw table title using vendor style."""
        style = self.vendor_style
        title_height = style.row_height * 1.5
        y = placement.start_y - title_height + 4

        bold_font = get_bold_font(style.font_family)
        c.setFont(bold_font, style.title_font_size)
        c.setFillColor(black)
        c.drawString(placement.start_x, y, title)

    def _draw_header_row(
        self,
        c: canvas.Canvas,
        cells: List[CellPlacement],
        template: TableTemplate
    ):
        """Draw header row with background using vendor style."""
        if not cells:
            return

        style = self.vendor_style

        # Draw background
        y_top = cells[0].y_top
        y_bottom = cells[0].y_bottom
        x_start = cells[0].x
        total_width = sum(cell.width for cell in cells)

        c.setFillColor(style.header_bg_color)
        c.rect(x_start, y_bottom, total_width, y_top - y_bottom, fill=True, stroke=False)

        # Draw text
        c.setFillColor(style.header_text_color)
        font_name = get_bold_font(style.font_family)
        font_size = style.header_font_size
        c.setFont(font_name, font_size)

        padding = style.cell_padding
        for cell in cells:
            text_y = cell.y_bottom + 3
            # Calculate available width for text (with padding on both sides)
            available_width = cell.width - (2 * padding)
            # Truncate text if needed
            display_text = truncate_text(cell.text, available_width, font_name, font_size, c)
            c.drawString(cell.x + padding, text_y, display_text)

    def _draw_data_row(
        self,
        c: canvas.Canvas,
        cells: List[CellPlacement],
        template: TableTemplate,
        is_subtotal: bool = False,
        row_index: int = 0
    ):
        """Draw a data row using vendor style."""
        if not cells:
            return

        style = self.vendor_style
        padding = style.cell_padding

        # Draw alternating row background if style uses it
        if style.grid_style == GridStyle.ALTERNATING_ROWS and row_index % 2 == 1:
            y_top = cells[0].y_top
            y_bottom = cells[0].y_bottom
            x_start = cells[0].x
            total_width = sum(cell.width for cell in cells)
            c.setFillColor(style.alternating_row_color)
            c.rect(x_start, y_bottom, total_width, y_top - y_bottom, fill=True, stroke=False)

        if is_subtotal:
            font_name = get_bold_font(style.font_family)
        else:
            font_name = style.font_family

        font_size = style.font_size
        c.setFont(font_name, font_size)
        c.setFillColor(black)

        for idx, cell in enumerate(cells):
            text_y = cell.y_bottom + 3
            spec = template.column_specs[idx]

            # Calculate available width for text (with padding on both sides)
            available_width = cell.width - (2 * padding)

            # Truncate text if needed
            display_text = truncate_text(cell.text, available_width, font_name, font_size, c)

            # Handle alignment
            if spec.alignment == "right":
                text_width = c.stringWidth(display_text, font_name, font_size)
                text_x = cell.x + cell.width - text_width - padding
            elif spec.alignment == "center":
                text_width = c.stringWidth(display_text, font_name, font_size)
                text_x = cell.x + (cell.width - text_width) / 2
            else:  # left
                text_x = cell.x + padding

            c.drawString(text_x, text_y, display_text)

    def _draw_grid_lines(
        self,
        c: canvas.Canvas,
        placement: TablePlacement,
        row_positions: List[RowPlacement],
        template: TableTemplate
    ):
        """Draw table grid lines using vendor style with degradation effects."""
        style = self.vendor_style
        c.setStrokeColor(style.grid_color)
        c.setLineWidth(style.grid_line_width)

        if not row_positions:
            return

        y_top = row_positions[0].y_top
        y_bottom = row_positions[-1].y_bottom
        header_y_bottom = row_positions[0].y_bottom if row_positions else y_top

        col_widths = self.layout_engine.compute_column_widths(template, placement.width)

        # Helper to draw line with degradation check
        def maybe_draw_line(x1, y1, x2, y2, always_draw=False):
            """Draw line if degradation allows or if always_draw is True."""
            if always_draw or not self._degradation or self._degradation.should_draw_grid_line():
                # Apply position jitter if degradation is active
                if self._degradation and self._degradation.params.position_jitter > 0:
                    x1, y1 = self._degradation.apply_position_jitter(x1, y1)
                    x2, y2 = self._degradation.apply_position_jitter(x2, y2)
                c.line(x1, y1, x2, y2)

        if style.grid_style == GridStyle.FULL_GRID:
            # Draw all horizontal and vertical lines
            for i, row_pos in enumerate(row_positions):
                # Always draw header separator and bottom line
                always = (i == 0 or i == len(row_positions) - 1)
                maybe_draw_line(placement.start_x, row_pos.y_bottom, placement.start_x + placement.width, row_pos.y_bottom, always)
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)

            # Vertical lines
            x = placement.start_x
            for i, width in enumerate(col_widths):
                # Always draw first and last vertical line
                always = (i == 0)
                maybe_draw_line(x, y_top, x, y_bottom, always)
                x += width
            maybe_draw_line(x, y_top, x, y_bottom, True)  # Right edge

        elif style.grid_style == GridStyle.HORIZONTAL_ONLY:
            # Only horizontal lines
            for i, row_pos in enumerate(row_positions):
                always = (i == 0 or i == len(row_positions) - 1)
                maybe_draw_line(placement.start_x, row_pos.y_bottom, placement.start_x + placement.width, row_pos.y_bottom, always)
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)

        elif style.grid_style == GridStyle.MINIMAL:
            # Just top, header separator, and bottom (always draw these)
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)
            maybe_draw_line(placement.start_x, header_y_bottom, placement.start_x + placement.width, header_y_bottom, True)
            maybe_draw_line(placement.start_x, y_bottom, placement.start_x + placement.width, y_bottom, True)

        elif style.grid_style == GridStyle.BOX_BORDERS:
            # Outer box plus header separator
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)
            maybe_draw_line(placement.start_x, header_y_bottom, placement.start_x + placement.width, header_y_bottom, True)
            maybe_draw_line(placement.start_x, y_bottom, placement.start_x + placement.width, y_bottom, True)
            maybe_draw_line(placement.start_x, y_top, placement.start_x, y_bottom, True)
            maybe_draw_line(placement.start_x + placement.width, y_top, placement.start_x + placement.width, y_bottom, True)

        elif style.grid_style == GridStyle.ALTERNATING_ROWS:
            # Just header lines (alternating rows handled in _draw_data_row)
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)
            maybe_draw_line(placement.start_x, header_y_bottom, placement.start_x + placement.width, header_y_bottom, True)
            maybe_draw_line(placement.start_x, y_bottom, placement.start_x + placement.width, y_bottom, True)

    def _render_vertical_kv(
        self,
        c: canvas.Canvas,
        doc_id: str,
        table_idx: int,
        template: TableTemplate,
        title: str,
        transactions: List[CashTransaction],
        vendor_system: str,
        rng,
    ) -> RenderedTable:
        """
        Render a vertical key-value form layout.

        Instead of columns, each transaction is rendered as:
        Date:        03/15/25
        Vendor:      Con Edison
        GL Code:     7000
        Amount:      1,250.00
        Memo:        FEB ELECTRIC
        """
        layout_type = LayoutType.VERTICAL_KV

        # Limit transactions for vertical layout (one form per transaction)
        max_txns = min(3, len(transactions))
        txns_to_render = transactions[:max_txns]

        # Calculate height: title + fields per transaction
        fields_per_txn = 5  # Date, Vendor, GL Code, Amount, Description
        row_height = template.row_height
        txn_block_height = (fields_per_txn + 1) * row_height  # +1 for spacing
        total_height = row_height * 2 + (txn_block_height * max_txns)

        # Check page break
        if not self.layout_engine.can_fit_on_current_page(total_height):
            self.layout_engine.start_new_page()

        # Sync canvas
        while self._current_canvas_page < self.layout_engine.current_page:
            c.showPage()
            self._current_canvas_page += 1

        table_id = f"{doc_id}__p{self.layout_engine.current_page}_t{table_idx}"
        start_x = self.layout.content_start_x
        start_y = self.layout_engine.current_y

        # Use vendor style for fonts
        style = self.vendor_style
        bold_font = get_bold_font(style.font_family)

        # Draw title
        c.setFont(bold_font, style.title_font_size)
        c.setFillColor(black)
        y = start_y - row_height * 1.5
        c.drawString(start_x, y + 4, title)

        y -= row_height * 0.5  # Gap after title

        rendered_rows: List[RenderedRow] = []
        row_idx = 0
        label_width = 120
        value_width = 200

        for txn in txns_to_render:
            # Create key-value pairs for this transaction
            kv_pairs = [
                ("Date:", txn.date.strftime("%m/%d/%y"), SemanticType.DATE),
                ("Vendor:", txn.vendor, SemanticType.VENDOR),
                ("GL Code:", txn.gl_code, SemanticType.ACCOUNT),
                ("Check #:", txn.check_number, SemanticType.OTHER),
                ("Amount:", f"${txn.amount:,.2f}", SemanticType.AMOUNT),
            ]

            for label, value, sem_type in kv_pairs:
                y -= row_height

                # Draw label (bold)
                c.setFont(bold_font, style.font_size)
                c.drawString(start_x + style.cell_padding, y + 3, label)

                # Draw value
                c.setFont(style.font_family, style.font_size)
                display_val = truncate_text(value, value_width, style.font_family, style.font_size, c)
                c.drawString(start_x + label_width, y + 3, display_val)

                # Create row metadata
                row_id = f"{table_id}_r{row_idx}"
                row_bbox = (start_x, y, start_x + label_width + value_width, y + row_height)

                rendered_cells = [
                    RenderedCell(
                        text=label,
                        page_index=self.layout_engine.current_page,
                        row_index=row_idx,
                        col_index=0,
                        bbox=(start_x, y, start_x + label_width, y + row_height),
                        semantic_type=SemanticType.OTHER,
                        row_type=RowType.BODY,
                    ),
                    RenderedCell(
                        text=value,
                        page_index=self.layout_engine.current_page,
                        row_index=row_idx,
                        col_index=1,
                        bbox=(start_x + label_width, y, start_x + label_width + value_width, y + row_height),
                        semantic_type=sem_type,
                        row_type=RowType.BODY,
                    ),
                ]

                rendered_rows.append(RenderedRow(
                    row_id=row_id,
                    table_id=table_id,
                    page_index=self.layout_engine.current_page,
                    row_index=row_idx,
                    bbox=row_bbox,
                    row_type=RowType.BODY,
                    cells=rendered_cells,
                ))
                row_idx += 1

            # Draw separator line between transactions
            y -= row_height * 0.5
            c.setStrokeColor(lightgrey)
            c.setLineWidth(0.5)
            c.line(start_x, y, start_x + label_width + value_width, y)
            y -= row_height * 0.3

        # Update layout engine position
        final_height = start_y - y + 10
        self.layout_engine.current_y -= final_height + 20
        self._page_has_content = True

        table_bbox = (start_x, y, start_x + label_width + value_width, start_y)

        return RenderedTable(
            table_id=table_id,
            doc_id=doc_id,
            page_index=self.layout_engine.current_page,
            bbox=table_bbox,
            table_type=template.table_type,
            layout_type=layout_type,
            is_table_region=True,
            vendor_system=vendor_system,
            title_text=title,
            fund="OPERATING",
            n_rows=len(rendered_rows),
            n_cols=2,  # Label and Value columns
            column_headers=["Label", "Value"],
            rows=rendered_rows,
            orientation=getattr(self, '_orientation', 'portrait'),
        )

    def _render_matrix(
        self,
        c: canvas.Canvas,
        doc_id: str,
        table_idx: int,
        template: TableTemplate,
        title: str,
        data: Any,  # Can be List[CashTransaction] or List[dict]
        vendor_system: str,
        rng,
    ) -> RenderedTable:
        """
        Render a matrix/cross-tab layout (e.g., Budget vs Actual).

        Format:
        Account         Current    YTD      Budget   Variance
        6000 Utilities    500.00  3,000.00  3,500.00   -500.00
        6100 Repairs      750.00  4,500.00  5,000.00   -500.00
        """
        layout_type = LayoutType.MATRIX

        # Handle dict data (budget tables) vs CashTransaction data
        headers = ["Account", "Current", "YTD", "Budget", "Variance"]
        matrix_rows = []

        if data and isinstance(data[0], dict):
            # Dict data from generate_budget_data - use pre-calculated values
            for row in data:
                matrix_rows.append([
                    row.get("account", ""),
                    f"{row.get('current', 0):,.2f}",
                    f"{row.get('ytd_actual', 0):,.2f}",
                    f"{row.get('ytd_budget', 0):,.2f}",
                    f"{row.get('variance', 0):+,.2f}",
                ])
            # Calculate totals
            total_current = sum(r.get("current", 0) for r in data)
            total_ytd = sum(r.get("ytd_actual", 0) for r in data)
            total_budget = sum(r.get("ytd_budget", 0) for r in data)
            total_variance = sum(r.get("variance", 0) for r in data)
        else:
            # CashTransaction data - group by GL code
            transactions = data
            gl_totals: Dict[str, float] = {}
            for txn in transactions:
                if txn.gl_code not in gl_totals:
                    gl_totals[txn.gl_code] = 0.0
                gl_totals[txn.gl_code] += txn.amount

            for gl_code, current in gl_totals.items():
                # Generate simulated YTD and Budget values
                ytd = current * rng.uniform(2.5, 4.0)
                budget = ytd * rng.uniform(0.9, 1.2)
                variance = budget - ytd
                matrix_rows.append([
                    gl_code,
                    f"{current:,.2f}",
                    f"{ytd:,.2f}",
                    f"{budget:,.2f}",
                    f"{variance:+,.2f}",
                ])
            total_current = sum(gl_totals.values())
            total_ytd = total_current * 3.0
            total_budget = total_ytd * 1.05
            total_variance = total_budget - total_ytd

        # Add total row
        matrix_rows.append([
            "TOTAL",
            f"{total_current:,.2f}",
            f"{total_ytd:,.2f}",
            f"{total_budget:,.2f}",
            f"{total_variance:+,.2f}",
        ])

        num_rows = len(matrix_rows) + 1  # +1 for header
        row_height = template.row_height
        total_height = row_height * 2 + num_rows * row_height

        # Check page break
        if not self.layout_engine.can_fit_on_current_page(total_height):
            self.layout_engine.start_new_page()

        while self._current_canvas_page < self.layout_engine.current_page:
            c.showPage()
            self._current_canvas_page += 1

        table_id = f"{doc_id}__p{self.layout_engine.current_page}_t{table_idx}"
        start_x = self.layout.content_start_x
        start_y = self.layout_engine.current_y
        table_width = self.layout.content_width

        # Use vendor style
        style = self.vendor_style
        bold_font = get_bold_font(style.font_family)
        padding = style.cell_padding

        # Column widths for matrix
        col_widths = [table_width * 0.30, table_width * 0.175, table_width * 0.175, table_width * 0.175, table_width * 0.175]

        # Draw title
        c.setFont(bold_font, style.title_font_size)
        c.setFillColor(black)
        y = start_y - row_height * 1.5
        c.drawString(start_x, y + 4, title)

        y -= row_height * 0.3

        # Draw header row
        header_y_top = y
        y -= row_height * 1.2
        header_y_bottom = y

        c.setFillColor(style.header_bg_color)
        c.rect(start_x, header_y_bottom, table_width, header_y_top - header_y_bottom, fill=True, stroke=False)

        c.setFillColor(style.header_text_color)
        c.setFont(bold_font, style.header_font_size)
        x = start_x
        for col_idx, (header, width) in enumerate(zip(headers, col_widths)):
            if col_idx == 0:
                c.drawString(x + padding, header_y_bottom + 3, header)
            else:
                # Right-align numeric columns
                text_width = c.stringWidth(header, bold_font, style.header_font_size)
                c.drawString(x + width - text_width - padding, header_y_bottom + 3, header)
            x += width

        rendered_rows: List[RenderedRow] = []

        # Add header to rendered rows
        row_idx = 0
        row_id = f"{table_id}_r{row_idx}"
        header_cells = []
        x = start_x
        for col_idx, (header, width) in enumerate(zip(headers, col_widths)):
            header_cells.append(RenderedCell(
                text=header,
                page_index=self.layout_engine.current_page,
                row_index=row_idx,
                col_index=col_idx,
                bbox=(x, header_y_bottom, x + width, header_y_top),
                semantic_type=SemanticType.OTHER,
                row_type=RowType.HEADER,
            ))
            x += width

        rendered_rows.append(RenderedRow(
            row_id=row_id,
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            row_index=row_idx,
            bbox=(start_x, header_y_bottom, start_x + table_width, header_y_top),
            row_type=RowType.HEADER,
            cells=header_cells,
        ))
        row_idx += 1

        # Draw data rows
        c.setFont(style.font_family, style.font_size)
        for data_row in matrix_rows:
            y_top = y
            y -= row_height
            y_bottom = y

            is_total = "TOTAL" in data_row[0]
            if is_total:
                c.setFont(bold_font, style.font_size)

            row_cells = []
            x = start_x
            for col_idx, (cell_text, width) in enumerate(zip(data_row, col_widths)):
                sem_type = SemanticType.ACCOUNT if col_idx == 0 else SemanticType.AMOUNT
                if col_idx == 0:
                    c.drawString(x + padding, y_bottom + 3, cell_text)
                else:
                    text_width = c.stringWidth(cell_text, style.font_family, style.font_size)
                    c.drawString(x + width - text_width - padding, y_bottom + 3, cell_text)

                row_cells.append(RenderedCell(
                    text=cell_text,
                    page_index=self.layout_engine.current_page,
                    row_index=row_idx,
                    col_index=col_idx,
                    bbox=(x, y_bottom, x + width, y_top),
                    semantic_type=sem_type,
                    row_type=RowType.SUBTOTAL_TOTAL if is_total else RowType.BODY,
                ))
                x += width

            rendered_rows.append(RenderedRow(
                row_id=f"{table_id}_r{row_idx}",
                table_id=table_id,
                page_index=self.layout_engine.current_page,
                row_index=row_idx,
                bbox=(start_x, y_bottom, start_x + table_width, y_top),
                row_type=RowType.SUBTOTAL_TOTAL if is_total else RowType.BODY,
                cells=row_cells,
            ))
            row_idx += 1

            if is_total:
                c.setFont(style.font_family, style.font_size)

        # Draw grid lines based on vendor style
        c.setStrokeColor(style.grid_color)
        c.setLineWidth(style.grid_line_width)

        if style.grid_style == GridStyle.FULL_GRID:
            # Horizontal lines
            c.line(start_x, header_y_top, start_x + table_width, header_y_top)
            c.line(start_x, header_y_bottom, start_x + table_width, header_y_bottom)
            c.line(start_x, y, start_x + table_width, y)
            # Vertical lines
            x = start_x
            for width in col_widths:
                c.line(x, header_y_top, x, y)
                x += width
            c.line(x, header_y_top, x, y)
        elif style.grid_style in [GridStyle.HORIZONTAL_ONLY, GridStyle.ALTERNATING_ROWS]:
            c.line(start_x, header_y_top, start_x + table_width, header_y_top)
            c.line(start_x, header_y_bottom, start_x + table_width, header_y_bottom)
            c.line(start_x, y, start_x + table_width, y)
        else:  # MINIMAL, BOX_BORDERS
            c.line(start_x, header_y_top, start_x + table_width, header_y_top)
            c.line(start_x, header_y_bottom, start_x + table_width, header_y_bottom)
            c.line(start_x, y, start_x + table_width, y)
            if style.grid_style == GridStyle.BOX_BORDERS:
                c.line(start_x, header_y_top, start_x, y)
                c.line(start_x + table_width, header_y_top, start_x + table_width, y)

        # Update layout engine
        self.layout_engine.current_y = y - 20
        self._page_has_content = True

        table_bbox = (start_x, y, start_x + table_width, start_y)

        return RenderedTable(
            table_id=table_id,
            doc_id=doc_id,
            page_index=self.layout_engine.current_page,
            bbox=table_bbox,
            table_type=template.table_type,
            layout_type=layout_type,
            is_table_region=True,
            vendor_system=vendor_system,
            title_text=title,
            fund="OPERATING",
            n_rows=len(rendered_rows),
            n_cols=len(headers),
            column_headers=headers,
            rows=rendered_rows,
            orientation=getattr(self, '_orientation', 'portrait'),
        )

    def _render_ragged(
        self,
        c: canvas.Canvas,
        doc_id: str,
        table_idx: int,
        template: TableTemplate,
        title: str,
        transactions: List[CashTransaction],
        vendor_system: str,
        rng,
    ) -> RenderedTable:
        """
        Render a ragged/pseudo-table layout with intentional misalignment.

        This simulates poorly formatted tables with:
        - Variable column positions
        - Wrapped text that bleeds into adjacent areas
        - Missing grid lines
        - Inconsistent indentation
        """
        layout_type = LayoutType.RAGGED

        # Use fewer transactions for ragged layout
        max_txns = min(8, len(transactions))
        txns_to_render = transactions[:max_txns]

        num_rows = len(txns_to_render) + 2  # header + data + total
        row_height = template.row_height
        total_height = row_height * 2 + num_rows * row_height * 1.3  # Extra height for jitter

        if not self.layout_engine.can_fit_on_current_page(total_height):
            self.layout_engine.start_new_page()

        while self._current_canvas_page < self.layout_engine.current_page:
            c.showPage()
            self._current_canvas_page += 1

        table_id = f"{doc_id}__p{self.layout_engine.current_page}_t{table_idx}"
        start_x = self.layout.content_start_x
        start_y = self.layout_engine.current_y
        table_width = self.layout.content_width * 0.85  # Narrower table

        # Use vendor style
        style = self.vendor_style
        bold_font = get_bold_font(style.font_family)
        padding = style.cell_padding

        # Draw title with slight offset
        title_offset = int(rng.uniform(-5, 10))
        c.setFont(bold_font, style.title_font_size)
        c.setFillColor(black)
        y = start_y - row_height * 1.5
        c.drawString(start_x + title_offset, y + 4, title)

        y -= row_height * 0.5

        # Ragged column positions (intentionally inconsistent)
        base_widths = [0.12, 0.25, 0.15, 0.28, 0.20]
        headers = ["Date", "Vendor", "GL Code", "Description", "Amount"]

        rendered_rows: List[RenderedRow] = []

        # Draw "header" with inconsistent formatting
        header_y_top = y
        y -= row_height * 1.1
        header_y_bottom = y

        # Partial header background (ragged style - only some columns)
        partial_bg_width = table_width * 0.6
        c.setFillColor(style.header_bg_color)
        c.rect(start_x, header_y_bottom, partial_bg_width, header_y_top - header_y_bottom, fill=True, stroke=False)

        c.setFillColor(style.header_text_color)
        c.setFont(bold_font, style.header_font_size)
        x = start_x
        header_cells = []
        for col_idx, (header, width_ratio) in enumerate(zip(headers, base_widths)):
            jitter = int(rng.uniform(-3, 3))
            width = table_width * width_ratio
            c.drawString(x + padding + jitter, header_y_bottom + 3, header)
            header_cells.append(RenderedCell(
                text=header,
                page_index=self.layout_engine.current_page,
                row_index=0,
                col_index=col_idx,
                bbox=(x, header_y_bottom, x + width, header_y_top),
                semantic_type=SemanticType.OTHER,
                row_type=RowType.HEADER,
            ))
            x += width

        rendered_rows.append(RenderedRow(
            row_id=f"{table_id}_r0",
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            row_index=0,
            bbox=(start_x, header_y_bottom, start_x + table_width, header_y_top),
            row_type=RowType.HEADER,
            cells=header_cells,
        ))

        # Draw data rows with ragged positioning
        row_idx = 1
        c.setFont(style.font_family, style.font_size)
        running_balance = 0.0

        for txn in txns_to_render:
            running_balance += txn.amount

            # Variable row height
            extra_height = int(rng.uniform(-2, 4))
            y_top = y
            y -= row_height + extra_height
            y_bottom = y

            row_data = [
                (txn.date.strftime("%m/%d/%y"), SemanticType.DATE),
                (txn.vendor, SemanticType.VENDOR),
                (txn.gl_code, SemanticType.ACCOUNT),
                (txn.description[:25] if len(txn.description) > 25 else txn.description, SemanticType.OTHER),
                (f"{txn.amount:,.2f}", SemanticType.AMOUNT),
            ]

            row_cells = []
            x = start_x
            for col_idx, ((cell_text, sem_type), width_ratio) in enumerate(zip(row_data, base_widths)):
                jitter = int(rng.uniform(-2, 2))
                width = table_width * width_ratio

                display_text = truncate_text(cell_text, width - 2 * padding, style.font_family, style.font_size, c)
                c.drawString(x + padding + jitter, y_bottom + 3, display_text)

                row_cells.append(RenderedCell(
                    text=cell_text,
                    page_index=self.layout_engine.current_page,
                    row_index=row_idx,
                    col_index=col_idx,
                    bbox=(x, y_bottom, x + width, y_top),
                    semantic_type=sem_type,
                    row_type=RowType.BODY,
                ))
                x += width

            rendered_rows.append(RenderedRow(
                row_id=f"{table_id}_r{row_idx}",
                table_id=table_id,
                page_index=self.layout_engine.current_page,
                row_index=row_idx,
                bbox=(start_x, y_bottom, start_x + table_width, y_top),
                row_type=RowType.BODY,
                cells=row_cells,
            ))
            row_idx += 1

        # Total row
        total_amount = sum(t.amount for t in txns_to_render)
        y_top = y
        y -= row_height
        y_bottom = y

        c.setFont(bold_font, style.font_size)
        # Only draw total in amount column area
        x = start_x
        for width_ratio in base_widths[:-1]:
            x += table_width * width_ratio

        c.drawString(x - 50, y_bottom + 3, "Total:")
        c.drawString(x + padding, y_bottom + 3, f"{total_amount:,.2f}")

        total_cells = []
        tx = start_x
        for col_idx, width_ratio in enumerate(base_widths):
            width = table_width * width_ratio
            text = ""
            if col_idx == 3:
                text = "Total:"
            elif col_idx == 4:
                text = f"{total_amount:,.2f}"
            total_cells.append(RenderedCell(
                text=text,
                page_index=self.layout_engine.current_page,
                row_index=row_idx,
                col_index=col_idx,
                bbox=(tx, y_bottom, tx + width, y_top),
                semantic_type=SemanticType.AMOUNT if col_idx == 4 else SemanticType.OTHER,
                row_type=RowType.SUBTOTAL_TOTAL,
            ))
            tx += width

        rendered_rows.append(RenderedRow(
            row_id=f"{table_id}_r{row_idx}",
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            row_index=row_idx,
            bbox=(start_x, y_bottom, start_x + table_width, y_top),
            row_type=RowType.SUBTOTAL_TOTAL,
            cells=total_cells,
        ))

        # Draw partial/ragged grid lines
        c.setStrokeColor(gray)
        c.setLineWidth(0.5)

        # Only top and bottom lines
        c.line(start_x, header_y_top, start_x + table_width * 0.9, header_y_top)
        c.line(start_x, y_bottom, start_x + table_width * 0.7, y_bottom)

        # Update layout engine
        self.layout_engine.current_y = y - 20
        self._page_has_content = True

        table_bbox = (start_x, y_bottom, start_x + table_width, start_y)

        return RenderedTable(
            table_id=table_id,
            doc_id=doc_id,
            page_index=self.layout_engine.current_page,
            bbox=table_bbox,
            table_type=template.table_type,
            layout_type=layout_type,
            is_table_region=True,
            vendor_system=vendor_system,
            title_text=title,
            fund="OPERATING",
            n_rows=len(rendered_rows),
            n_cols=len(headers),
            column_headers=headers,
            rows=rendered_rows,
            orientation=getattr(self, '_orientation', 'portrait'),
        )
