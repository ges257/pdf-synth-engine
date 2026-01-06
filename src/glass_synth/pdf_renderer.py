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

# ===== V3 PATTERNS FROM REAL PDF ANALYSIS =====

# Page number formats (from real PDFs - 1403 found)
PAGE_NUMBER_FORMATS = [
    lambda p, t: f"- {p} -",
    lambda p, t: f"({p})",
    lambda p, t: f"Page {p}",
    lambda p, t: f"Page {p} of {t}",
    lambda p, t: f"{p} of {t}",
]

# Multi-box indicators (from real PDFs - 2053 found)
MULTI_BOX_INDICATORS = {
    'dashed_total': [
        "------TOTAL------",
        "------SUBTOTAL------",
        "------- TOTAL -------",
        "------NET------",
    ],
    'prepared_for': [
        "--- PREPARED FOR ---",
        "--- PREPARED BY ---",
        "--- PREPARED AS OF ---",
    ],
    'section_markers': [
        "*** CASH AVAILABLE ***",
        "*** END OF REPORT ***",
        "*** CONTINUED ***",
        "*** SEE NOTES ***",
    ],
    'underlines': [
        "______________________",
        "_____________",
        "--------------------",
    ],
    'section_headers': [
        "----------CURRENT MONTH------",
        "----------YEAR TO DATE------",
        "---------PRIOR PERIOD---------",
        "========== SUMMARY ==========",
    ],
}

# Section title templates for PAGE_HEADER (from AKAM/Lindenwood analysis)
SECTION_TITLE_TEMPLATES = [
    "Collection Status {building}",
    "Tenant Ledger {building}",
    "Receivables Aging {building}",
    "Cash Receipts {building}",
    "Cash Disbursements {building}",
    "Income Statement {building}",
    "Balance Sheet {building}",
    "Budget Comparison {building}",
    "General Ledger {building}",
    "Unpaid Bills {building}",
    "Arrears Report {building}",
]

# Multi-line header definitions (from real PDFs)
MULTILINE_HEADER_PATTERNS = {
    "CASH_IN": [
        (
            ["", "", "", "", "Opening", "Current", "", "Closing", "", ""],
            ["BLD-TEN", "UNIT", "RESIDENT", "BASE", "BALANCE", "CHARGES", "PAYMENTS", "BALANCE", "SHARES", "LEASE"]
        ),
        (
            ["", "", "", "Opening", "Current", "Payments", "Closing", ""],
            ["Tenant", "Status", "Balance", "Charges", "Received", "Balance", "Legal"]
        ),
    ],
    "CASH_OUT": [
        (
            ["Invoice", "Check", "", "", "", "", "", ""],
            ["Date", "Date", "VEND", "Vendor", "Invoice #", "P/O", "GL Code", "Amount"]
        ),
        (
            ["", "", "", "", "", "Running"],
            ["Date", "CK NO", "Paid To", "GL", "Description", "Amount", "Balance"]
        ),
    ],
    "BUDGET": [
        (
            ["", "Current", "YTD", "YTD", "Annual", ""],
            ["Account", "Month", "Actual", "Budget", "Budget", "Variance"]
        ),
    ],
    "AGING": [
        (
            ["", "", "Days Outstanding", "", "", "", ""],
            ["Unit", "Owner", "Current", "30 Days", "60 Days", "90+ Days", "Total"]
        ),
    ],
}

# Subtotal keywords (required for SUBTOTAL_TOTAL classification)
SUBTOTAL_KEYWORDS = {
    "TOTAL", "SUBTOTAL", "SUB-TOTAL", "GRAND TOTAL", "NET TOTAL",
    "TOTAL:", "SUBTOTAL:", "TOTALS", "BALANCE END OF PERIOD",
    # Phase5B additions (new keywords only)
    "** TOTAL **", "Subtotal", "Total", "Total Income Statement",
    "CONSOLIDATED TOTAL", "ENTITY TOTAL", "NET CASH FLOW",
}

# ===== PHASE5B ENHANCEMENTS =====

# GL Code Format Variations (from Phase5B research)
# Different platforms use different GL code formats
GL_CODE_FORMATS = [
    lambda code: f"{code:04d}-00",       # Yardi: 5010-00
    lambda code: f"GL-{code:03d}",        # AppFolio: GL-501
    lambda code: str(code),               # MDS: 5010
    lambda code: f"{code:04d}",           # Simple: 5010
    lambda code: f"{code:05d}",           # 5-digit: 05010
]

# Section Title Case Styles (from Phase5B research)
# Different platforms use different case styles for PAGE_HEADER
TITLE_CASE_STYLES = [
    lambda s: s.upper(),                  # Yardi: COLLECTION STATUS
    lambda s: s.title(),                  # AppFolio: Collection Status
    lambda s: s,                          # As-is
    lambda s: "  " + s.upper(),           # MRI: (indented) COLLECTION STATUS
]

# Multi-line header probability (40% per Phase5B research)
MULTILINE_HEADER_PROBABILITY = 0.4

# ===== VENDOR-SPECIFIC HEADER TEMPLATES (Phase5A Deep Variations) =====
# Based on GLASS_Phase5A_Deepest_Variations.md research
# Target distribution from real PDFs: 14%/14%/36%/21%/14% (1-5 lines)
# Max 5 lines per research

VENDOR_HEADER_TEMPLATES = {
    'YARDI': {
        # Professional accounting, verbose headers (3-4 lines)
        'line_counts': [3, 3, 3, 4, 4],  # 60% 3-line, 40% 4-line
        'templates': [
            # 3-line format
            ["{building} | {address}",
             "{company} | Period: {period}",
             "Page {page} of {total} // {title}"],
            # 4-line format with manager
            ["{building}",
             "{address}",
             "Manager: {manager} | Period: {period}",
             "Page {page} of {total} // {title}"],
        ],
        'manager_included': True,
        'page_format': 'Page {page} of {total}',
    },
    'APPFOLIO': {
        # Modern SaaS, MINIMALIST headers (1-3 lines)
        'line_counts': [1, 1, 2, 2, 3],  # 40% 1-line, 40% 2-line, 20% 3-line
        'templates': [
            # 1-line ultra-compact
            ["{building}"],
            # 2-line compact
            ["{building}",
             "Page {page} // {title}"],
            # 3-line standard
            ["{building}",
             "Report Period: {period}",
             "Page {page} // {title}"],
        ],
        'manager_included': False,
        'page_format': 'Page {page}',
    },
    'DOUGLAS_ELLIMAN': {
        # Luxury minimal (1-2 lines)
        'line_counts': [1, 1, 1, 2, 2],  # 60% 1-line, 40% 2-line
        'templates': [
            # 1-line
            ["{building}"],
            # 2-line
            ["{building}",
             "Page {page}"],
        ],
        'manager_included': False,
        'page_format': 'Page {page}',
    },
    'BUILDIUM': {
        # High variation (3-5 lines)
        'line_counts': [3, 3, 4, 4, 5],  # 40% 3-line, 40% 4-line, 20% 5-line
        'templates': [
            # 3-line
            ["{building} | {address}",
             "Period: {period}",
             "Page {page} // {title}"],
            # 4-line
            ["{company}",
             "{building}",
             "Period: {period}",
             "Page {page} // {title}"],
            # 5-line verbose (max)
            ["{company}",
             "{building}",
             "{address}",
             "Prepared by: {manager}",
             "Page {page} of {total} // {title}"],
        ],
        'manager_included': True,
        'page_format': 'Page {page} // {title}',
    },
    'OTHER': {
        # Hierarchical/verbose (4-5 lines)
        'line_counts': [4, 4, 4, 5, 5],  # 60% 4-line, 40% 5-line
        'templates': [
            # 4-line
            ["{company}",
             "Property: {building}",
             "Period: {period}",
             "Page {page} // {title}"],
            # 5-line (max per research)
            ["{company}",
             "Property: {building}",
             "Prepared by: {manager}",
             "{title}",
             "Period: {period} | Page {page} of {total}"],
        ],
        'manager_included': True,
        'page_format': 'Page {page} of {total}',
    },
    # AKAM - similar to YARDI (3-4 lines)
    'AKAM_NEW': {
        'line_counts': [3, 3, 3, 4, 4],
        'templates': [
            # 3-line
            ["{building}",
             "{company} | Period: {period}",
             "Page {page} of {total} // {title}"],
            # 4-line
            ["{building}",
             "{address}",
             "Manager: {manager} | {period}",
             "Page {page} of {total} // {title}"],
        ],
        'manager_included': True,
        'page_format': 'Page {page} of {total}',
    },
}

# Map existing vendor names to template keys
VENDOR_TEMPLATE_MAP = {
    'AKAM_NEW': 'AKAM_NEW',
    'AKAM_OLD': 'AKAM_NEW',
    'DOUGLAS': 'DOUGLAS_ELLIMAN',
    'DOUGLAS_ELLIMAN': 'DOUGLAS_ELLIMAN',
    'FIRSTSERVICE': 'APPFOLIO',  # Similar minimal style
    'LINDENWOOD': 'BUILDIUM',  # Similar variation
    'MDS': 'YARDI',  # Similar professional style
    'ORSID': 'BUILDIUM',  # Similar variation
    'YARDI': 'YARDI',
    'APPFOLIO': 'APPFOLIO',
    'BUILDIUM': 'BUILDIUM',
    'MRI': 'OTHER',
    'OTHER': 'OTHER',
}


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
        self._gl_code_format = None  # Phase5B: Document-level GL code format
        self._template_state = None  # Phase5A: Document-level template state (identical headers)

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

    def _format_gl_code(self, gl_code: str) -> str:
        """Format GL code using the document's selected format (Phase5B enhancement)."""
        if self._gl_code_format is None:
            return gl_code
        try:
            # Extract numeric part of GL code for formatting
            numeric_part = int(''.join(c for c in gl_code if c.isdigit()) or '0')
            return self._gl_code_format(numeric_part)
        except (ValueError, TypeError):
            return gl_code  # Return original if formatting fails

    def _initialize_template_state(
        self,
        vendor_system: str,
        building_name: str,
        title: str,
        rng
    ) -> None:
        """
        Initialize document-level template state (Phase5A enhancement).

        Called once at the start of render_document to ensure IDENTICAL
        headers across all pages (only page number changes).

        Args:
            vendor_system: Vendor system name (e.g., "AKAM_NEW", "YARDI")
            building_name: Building/owner corporation name
            title: Report/schedule title
            rng: Random number generator
        """
        from .companies import get_random_manager, get_random_company

        # Map vendor to template key
        template_key = VENDOR_TEMPLATE_MAP.get(vendor_system, 'OTHER')
        vendor_config = VENDOR_HEADER_TEMPLATES.get(template_key, VENDOR_HEADER_TEMPLATES['OTHER'])

        # Select number of lines based on distribution
        line_count = rng.choice(vendor_config['line_counts'])

        # Find a template with the right number of lines (or closest)
        templates = vendor_config['templates']
        matching_templates = [t for t in templates if len(t) == line_count]
        if not matching_templates:
            # Fall back to any template
            matching_templates = templates
        selected_template = rng.choice(matching_templates)

        # Get manager name if this vendor includes it
        manager_name = get_random_manager(rng) if vendor_config['manager_included'] else None

        # Generate period (e.g., "December 2025")
        months = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        period_month = rng.choice(months)
        period_year = 2025
        period = f"{period_month} {period_year}"

        # Get company name from building (or use a management company)
        company = get_random_company(rng)
        company_name = company.name

        # Generate a building address
        street_nums = rng.integers(100, 999)
        street_suffixes = ["Street", "Avenue", "Boulevard", "Place", "Drive"]
        street_names = ["Park", "Madison", "Lexington", "Fifth", "Third", "Second",
                        "East 72nd", "West 86th", "Central Park", "Broadway"]
        address = f"{street_nums} {rng.choice(street_names)} {rng.choice(street_suffixes)}, New York, NY"

        # Store the template state
        self._template_state = {
            'template_key': template_key,
            'template_lines': selected_template,
            'building': building_name,
            'company': company_name,
            'manager': manager_name,
            'period': period,
            'address': address,
            'title': title,
            'page_format': vendor_config['page_format'],
        }

    def _generate_page_header_text(
        self,
        template: 'TableTemplate',
        building_name: str,
        rng
    ) -> Optional[str]:
        """
        Generate PAGE_HEADER text (section/report title).

        PAGE_HEADER appears before column headers and describes the section.
        Examples: "Collection Status 245 East 72nd Street Corp"
                  "Tenant Ledger Park Terrace Gardens"

        Args:
            template: Table template for context
            building_name: Building name to include
            rng: Random number generator

        Returns:
            Section title text or None if not generating
        """
        # 70% of tables have a PAGE_HEADER
        if rng.random() > 0.7:
            return None

        # Select template based on table type
        table_type = template.table_type.value
        if table_type == "CASH_IN":
            templates = [
                "Collection Status {building}",
                "Tenant Ledger {building}",
                "Receivables Aging {building}",
                "Cash Receipts {building}",
            ]
        elif table_type == "CASH_OUT":
            templates = [
                "Cash Disbursements {building}",
                "Accounts Payable {building}",
                "Check Register {building}",
            ]
        elif table_type == "BUDGET":
            templates = [
                "Income Statement {building}",
                "Budget Comparison {building}",
                "Operating Statement {building}",
            ]
        elif table_type == "AGING":
            templates = [
                "Arrears Report {building}",
                "Aging Summary {building}",
                "Delinquency Report {building}",
            ]
        elif table_type == "GL":
            templates = [
                "General Ledger {building}",
                "Account Detail {building}",
            ]
        else:
            templates = SECTION_TITLE_TEMPLATES

        selected = rng.choice(templates)
        text = selected.format(building=building_name)

        # Apply random title case style (Phase5B enhancement)
        case_style = rng.choice(TITLE_CASE_STYLES)
        return case_style(text)

    def _generate_template_text(
        self,
        page_num: int,
        total_pages: int,
        company_name: str,
        rng
    ) -> Tuple[List[str], str]:
        """
        Generate TEMPLATE text for page header and footer (Phase5A enhanced).

        TEMPLATE rows are design layer elements that repeat IDENTICALLY on every page.
        Uses vendor-specific templates with 1-6 header lines.
        Only the page number changes between pages.

        Args:
            page_num: Current page number (1-indexed)
            total_pages: Total pages in document
            company_name: Company/building name (fallback if no template state)
            rng: Random number generator

        Returns:
            Tuple of (header_lines: List[str], footer_text: str)
            - header_lines: 1-6 lines of header text (TEMPLATE rows)
            - footer_text: Page number footer (TEMPLATE row)
        """
        # If template state not initialized, fall back to simple header
        if self._template_state is None:
            header_lines = [company_name]
            fmt = rng.choice(PAGE_NUMBER_FORMATS)
            footer_text = fmt(page_num, total_pages)
            return header_lines, footer_text

        state = self._template_state

        # Format each template line with stored values (substituting page number)
        header_lines = []
        for template_line in state['template_lines']:
            formatted = template_line.format(
                building=state['building'],
                company=state['company'],
                manager=state['manager'] or "",
                period=state['period'],
                address=state['address'],
                title=state['title'],
                page=page_num,
                total=total_pages,
                code=rng.integers(1000, 9999),  # Account code if needed
                entity=state['building'],  # Entity alias
            )
            header_lines.append(formatted)

        # Generate footer with page number (always present)
        footer_text = state['page_format'].format(
            page=page_num,
            total=total_pages,
            title=state['title']
        )

        return header_lines, footer_text

    def _compute_header_footer_positions(
        self,
        placement_start_y: float,
        table_bbox: Tuple[float, float, float, float],
        header_lines: List[str],
        footer_text: str,
        line_height: float = 15.0,
        padding: float = 5.0,
        margin: float = 10.0,
    ) -> Dict:
        """
        Compute clamped header and footer positions for both drawing AND GT.

        This is the SINGLE SOURCE OF TRUTH for header/footer coordinates.
        Both _draw_template_header() and GT creation must use these positions.

        Header placement strategy:
        - Headers draw BELOW placement_start_y (going down into page)
        - If header block would extend below margin, shift UP to fit
        - base_header_y = placement_start_y - padding, then lines descend

        Footer placement strategy:
        - Footer draws below table_bbox bottom
        - If footer would go below margin, clamp to margin

        Args:
            placement_start_y: Top of table content area (ReportLab coords)
            table_bbox: (x0, y0, x1, y1) where y0 is bottom, y1 is top
            header_lines: List of header text lines
            footer_text: Footer text (may be empty)
            line_height: Height per line in points
            padding: Padding between elements
            margin: Minimum distance from page edge

        Returns:
            Dict with:
                header_line_positions: [(y_baseline, y_top, y_bottom), ...] for each line
                header_bbox: (y_bottom, y_top) of entire header block
                footer_position: (y_baseline, y_top, y_bottom) or None
                footer_bbox: (y_bottom, y_top) or None
        """
        page_height = self.layout_engine.layout.page_height
        num_header_lines = len(header_lines)

        result = {
            "header_line_positions": [],
            "header_bbox": None,
            "footer_position": None,
            "footer_bbox": None,
        }

        # === HEADER POSITIONS ===
        if num_header_lines > 0:
            # Compute header block dimensions
            header_block_height = (num_header_lines - 1) * line_height + padding * 2

            # Initial placement: first line at placement_start_y - padding
            # Lines descend from there
            initial_base_y = placement_start_y - padding

            # Compute where the bottom of the header block would be
            header_block_bottom = initial_base_y - (num_header_lines - 1) * line_height - padding

            # Check if header block fits above the margin
            if header_block_bottom < margin:
                # Shift entire header block UP to fit
                shift_amount = margin - header_block_bottom
                initial_base_y += shift_amount

            # Also ensure header doesn't exceed page top
            if initial_base_y > page_height - margin:
                initial_base_y = page_height - margin

            # Compute final line positions
            header_line_positions = []
            for line_idx in range(num_header_lines):
                y_baseline = initial_base_y - (line_idx * line_height)
                y_top = y_baseline + padding  # Approximate top of text
                y_bottom = y_baseline - line_height + padding  # Approximate bottom
                header_line_positions.append((y_baseline, y_top, y_bottom))

            result["header_line_positions"] = header_line_positions

            # Header bbox: from top of first line to bottom of last line
            if header_line_positions:
                header_y_top = header_line_positions[0][1]  # Top of first line
                header_y_bottom = header_line_positions[-1][2]  # Bottom of last line
                result["header_bbox"] = (header_y_bottom, header_y_top)

        # === FOOTER POSITIONS ===
        if footer_text:
            # Footer goes below table
            table_bottom = table_bbox[1]  # y0 is bottom in ReportLab
            footer_y_baseline = table_bottom - 25  # 25pt below table

            # Clamp to stay above margin
            if footer_y_baseline < margin + line_height:
                footer_y_baseline = margin + line_height

            footer_y_top = footer_y_baseline + padding
            footer_y_bottom = footer_y_baseline - line_height + padding

            result["footer_position"] = (footer_y_baseline, footer_y_top, footer_y_bottom)
            result["footer_bbox"] = (footer_y_bottom, footer_y_top)

        return result

    def _add_template_rows(
        self,
        rendered_rows: List['RenderedRow'],
        table_id: str,
        page_index: int,
        building_name: str,
        placement_start_x: float,
        placement_start_y: float,
        placement_width: float,
        table_bbox: Tuple[float, float, float, float],
        rng
    ) -> None:
        """
        Add TEMPLATE rows to a rendered table (Phase5A: multi-line headers + footer).

        This method modifies rendered_rows in-place, inserting header lines at the
        beginning and appending a footer at the end.

        Args:
            rendered_rows: List of RenderedRow to modify
            table_id: Table identifier
            page_index: Current page index
            building_name: Building name for template
            placement_start_x: Table start X position
            placement_start_y: Table start Y position
            placement_width: Table width
            table_bbox: Table bounding box (x0, y0, x1, y1)
            rng: Random number generator
        """
        total_pages_estimate = max(self.layout_engine.current_page + 1, 10)
        header_lines, footer_text = self._generate_template_text(
            page_num=page_index + 1,
            total_pages=total_pages_estimate,
            company_name=building_name,
            rng=rng
        )

        # NOTE: This function previously created GT for TEMPLATE rows (header/footer)
        # but these simpler table types don't actually DRAW template headers/footers.
        # Creating GT for non-rendered content causes mismatches between GT and PDF.
        # Solution: Do not create phantom TEMPLATE GT.
        #
        # The render_document() path DOES draw templates and handles its own GT creation
        # with coordinates that match the actual drawing.
        pass

    def _get_template_header_height(self, header_lines: List[str], style: 'VendorStyle') -> float:
        """
        Calculate template header height based on number of lines and style.

        This is used to offset the table content downward to prevent headers
        from being cut off at the top of the page.

        Args:
            header_lines: List of header text lines
            style: Vendor style with grid_style attribute

        Returns:
            Height in points to reserve for the template header
        """
        if not header_lines:
            return 0

        num_lines = len(header_lines)
        from glass_synth.vendor_styles import GridStyle

        if style.grid_style == GridStyle.LINDENWOOD_TWO_SECTION:
            # Two-section layout: LEFT box + RIGHT text needs more height
            left_lines = min(3, num_lines)  # First 3 lines in left box
            return 25 + left_lines * 16 + 20  # ~77-93pt
        else:
            # Standard styles: simple calculation
            return 20 + num_lines * 15  # ~50-95pt

    def _calculate_rows_per_page(
        self,
        template: 'TableTemplate',
        total_data_rows: int,
        num_header_rows: int,
        is_first_chunk: bool,
        header_lines: List[str],
        has_page_header: bool,
    ) -> int:
        """
        Calculate how many data rows fit on the current page.

        Args:
            template: Table template with row_height
            total_data_rows: Total number of data rows to render
            num_header_rows: Number of column header rows (1 or 2)
            is_first_chunk: True if this is the first chunk (has template header)
            header_lines: Template header lines (for height calculation)
            has_page_header: Whether PAGE_HEADER will be drawn

        Returns:
            Number of data rows that fit on this page
        """
        layout = self.layout_engine.layout
        available_height = layout.content_height

        # Subtract template header space (only on first chunk)
        if is_first_chunk and header_lines:
            template_header_height = self._get_template_header_height(header_lines, self.vendor_style)
            available_height -= template_header_height

        # Subtract PAGE_HEADER space
        if has_page_header:
            available_height -= template.row_height * 1.5 + 10

        # Subtract column header rows
        available_height -= num_header_rows * template.row_height * 1.2

        # Subtract bottom padding
        available_height -= 20

        # Calculate how many data rows fit
        rows_that_fit = int(available_height / template.row_height)

        # Ensure at least 1 row fits (to make progress)
        return max(1, min(rows_that_fit, total_data_rows))

    def _draw_template_header(
        self,
        c: canvas.Canvas,
        header_lines: List[str],
        placement_start_x: float,
        placement_start_y: float,
        placement_width: float,
        style: 'VendorStyle',
        header_positions: Dict = None,
    ) -> Tuple[float, float, float, float]:
        """
        Draw TEMPLATE header text on the canvas using pre-computed positions.

        IMPORTANT: Use _compute_header_footer_positions() to get header_positions
        before calling this function. This ensures drawing uses the same clamped
        coordinates as GT creation.

        Args:
            c: ReportLab canvas
            header_lines: List of header text lines to draw
            placement_start_x: Table start X position
            placement_start_y: Table start Y position (used for fallback only)
            placement_width: Table width
            style: Vendor style for fonts and colors
            header_positions: Pre-computed positions from _compute_header_footer_positions()
                             If None, falls back to legacy computation (NOT RECOMMENDED)

        Returns:
            Bounding box (x0, y0, x1, y1) of the template header area
        """
        from glass_synth.vendor_styles import get_bold_font, GridStyle

        line_height = 15
        padding = 5
        num_lines = len(header_lines)

        # Get header line positions from pre-computed dict
        # REQUIRED: header_positions must be provided by caller via _compute_header_footer_positions()
        # This ensures drawing and GT use identical coordinates (no silent mismatch)
        if not header_positions or not header_positions.get("header_line_positions"):
            raise ValueError(
                "_draw_template_header() requires header_positions from "
                "_compute_header_footer_positions(). Legacy fallback removed to prevent "
                "coordinate mismatch between drawing and GT."
            )

        line_positions = header_positions["header_line_positions"]
        header_bbox_rl = header_positions.get("header_bbox")
        if header_bbox_rl:
            box_bottom, box_top = header_bbox_rl
        else:
            box_top = placement_start_y
            box_bottom = box_top - num_lines * line_height

        template_bbox = (
            placement_start_x,
            box_bottom,
            placement_start_x + placement_width,
            box_top
        )

        # Handle LINDENWOOD_TWO_SECTION style with two-section layout
        if style.grid_style == GridStyle.LINDENWOOD_TWO_SECTION:
            self._draw_lindenwood_two_section_header(
                c, header_lines, placement_start_x, placement_start_y, placement_width, style
            )
            return template_bbox

        # Draw simple centered text lines (default for other styles)
        bold_font = get_bold_font(style.font_family)
        c.setFont(bold_font, style.header_font_size)
        c.setFillColor(style.header_text_color)

        # Draw each line at its pre-computed position
        for line_idx, header_line in enumerate(header_lines):
            if line_idx >= len(line_positions):
                break
            y_baseline = line_positions[line_idx][0]

            # Center the text
            text_width = c.stringWidth(header_line, bold_font, style.header_font_size)
            text_x = placement_start_x + (placement_width - text_width) / 2
            c.drawString(text_x, y_baseline, header_line)

        return template_bbox

    def _draw_nested_box_header(
        self,
        c: canvas.Canvas,
        header_lines: List[str],
        placement_start_x: float,
        placement_start_y: float,
        placement_width: float,
        style: 'VendorStyle',
    ) -> None:
        """
        Draw TEMPLATE header with nested box structure (DOUBLE_BOX_NESTED).

        Uses ReportLab line drawing instead of Unicode characters for consistent rendering.

        Creates structure:
        +--------------------------------------------------+
        |  +============================================+  |
        |  | [Header Line 1]                            |  |
        |  | [Header Line 2]                            |  |
        |  | - - - - - - - - - - - - - - - - - - - - -  |  |
        |  | [Header Line 3]                            |  |
        |  +============================================+  |
        +--------------------------------------------------+
        """
        from glass_synth.vendor_styles import get_bold_font

        font_name = style.font_family
        bold_font = get_bold_font(font_name)
        font_size = style.font_size
        line_height = 14

        # Layout dimensions
        outer_padding = 10
        inner_padding = 8

        # Calculate box dimensions
        num_lines = len(header_lines)
        # Add extra height for separator line if needed
        has_separator = num_lines > 3
        content_lines = num_lines + (1 if has_separator else 0)

        inner_box_height = content_lines * line_height + inner_padding * 2
        outer_box_height = inner_box_height + outer_padding * 2

        # Box positions - draw BELOW placement_start_y (in reserved header space)
        outer_x = placement_start_x
        outer_y_top = placement_start_y - 5  # Start just below content area top
        outer_y_bottom = outer_y_top - outer_box_height
        outer_width = placement_width

        inner_x = outer_x + outer_padding
        inner_y_top = outer_y_top - outer_padding
        inner_y_bottom = inner_y_top - inner_box_height
        inner_width = outer_width - outer_padding * 2

        # Draw outer box (thin line)
        c.setStrokeColor(style.grid_color)
        c.setLineWidth(0.5)
        c.rect(outer_x, outer_y_bottom, outer_width, outer_box_height, fill=False, stroke=True)

        # Draw inner box (thicker line - double effect)
        c.setLineWidth(1.5)
        c.rect(inner_x, inner_y_bottom, inner_width, inner_box_height, fill=False, stroke=True)

        # Draw header content lines (centered)
        c.setFont(bold_font, font_size)
        c.setFillColor(style.header_text_color)

        separator_idx = num_lines // 2 if has_separator else -1
        current_line = 0

        for idx, header_line in enumerate(header_lines):
            text_y = inner_y_top - inner_padding - (current_line + 1) * line_height
            text_width = c.stringWidth(header_line, bold_font, font_size)
            text_x = inner_x + (inner_width - text_width) / 2
            c.drawString(text_x, text_y, header_line)
            current_line += 1

            # Add dashed separator after middle line
            if idx == separator_idx:
                sep_y = inner_y_top - inner_padding - (current_line + 0.5) * line_height
                c.setDash([3, 3])  # Dashed line
                c.setLineWidth(0.5)
                c.line(inner_x + inner_padding, sep_y, inner_x + inner_width - inner_padding, sep_y)
                c.setDash([])  # Reset to solid
                current_line += 1

    def _draw_lindenwood_two_section_header(
        self,
        c: canvas.Canvas,
        header_lines: List[str],
        placement_start_x: float,
        placement_start_y: float,
        placement_width: float,
        style: 'VendorStyle',
    ) -> None:
        """
        Draw Lindenwood two-section TEMPLATE header:
        - LEFT side: Thick-bordered box with org name, report type, period (first 3 lines)
        - RIGHT side: Plain text with address, page number (remaining lines)

        Uses ReportLab line drawing for consistent rendering (no Unicode characters).
        """
        from glass_synth.vendor_styles import get_bold_font

        font_name = style.font_family
        bold_font = get_bold_font(font_name)
        font_size = style.font_size
        line_height = 16
        padding = 8

        # Split header lines: first 3 go in LEFT box, rest go in RIGHT text
        left_lines = header_lines[:3] if len(header_lines) >= 3 else header_lines
        right_lines = header_lines[3:] if len(header_lines) > 3 else []

        # Calculate dimensions
        num_left_lines = len(left_lines)
        num_right_lines = len(right_lines)
        max_lines = max(num_left_lines, num_right_lines, 3)
        section_height = max_lines * line_height + padding * 2 + 10

        # Layout: 40% left box, 60% right text
        left_width = placement_width * 0.4
        right_width = placement_width * 0.6

        # Positions - draw BELOW placement_start_y (in reserved header space)
        x = placement_start_x
        y_top = placement_start_y - 5  # Start just below content area top
        y_bottom = y_top - section_height

        # Draw outer frame (thin border around entire header section)
        c.setStrokeColor(style.grid_color)
        c.setLineWidth(0.5)
        c.rect(x, y_bottom, placement_width, section_height, fill=False, stroke=True)

        # Draw LEFT box (thick border, inset slightly)
        left_box_x = x + 5
        left_box_y = y_bottom + 5
        left_box_width = left_width - 10
        left_box_height = section_height - 10
        c.setLineWidth(1.5)
        c.rect(left_box_x, left_box_y, left_box_width, left_box_height, fill=False, stroke=True)

        # Draw vertical divider between LEFT and RIGHT
        divider_x = x + left_width
        c.setLineWidth(0.5)
        c.line(divider_x, y_bottom, divider_x, y_top)

        # Draw LEFT text (centered in box)
        c.setFont(bold_font, font_size)
        c.setFillColor(style.header_text_color)
        for idx, line in enumerate(left_lines):
            text_y = y_top - padding - (idx + 1) * line_height
            text_width = c.stringWidth(line, bold_font, font_size)
            text_x = left_box_x + (left_box_width - text_width) / 2
            c.drawString(text_x, text_y, line)

        # Draw RIGHT text (plain, left-aligned with label)
        right_start_x = divider_x + 10
        c.setFont(font_name, font_size)  # Regular font for right side

        # Add "--- PREPARED FOR ---" label if we have right content
        if right_lines:
            label_y = y_top - padding - line_height
            c.drawString(right_start_x, label_y, "--- PREPARED FOR ---")

            # Draw right content lines below label
            for idx, line in enumerate(right_lines):
                text_y = y_top - padding - (idx + 2) * line_height
                c.drawString(right_start_x, text_y, line)
        else:
            # No right lines, just show placeholder
            label_y = y_top - padding - line_height * 2
            c.drawString(right_start_x, label_y, "Property Report")

    def _should_use_multiline_headers(self, template: 'TableTemplate', rng) -> bool:
        """Determine if this table should use multi-line headers (40% chance)."""
        return rng.random() < MULTILINE_HEADER_PROBABILITY

    def _generate_multiline_header_row(
        self,
        template: 'TableTemplate',
        column_headers: List[str],
        rng
    ) -> Optional[List[str]]:
        """
        Generate a super-header row for multi-line headers (Phase5B enhancement).

        Creates category labels above the main column headers based on semantic types.
        Example: ["", "", "Opening", "Current", "Payments", "Closing", ""]
                 ["Tenant", "Status", "Balance", "Charges", "Received", "Balance", "Legal"]

        Args:
            template: Table template with column specs
            column_headers: The main column header names
            rng: Random number generator

        Returns:
            List of super-header labels (same length as column_headers), or None
        """
        table_type = template.table_type.value

        # Check if we have patterns for this table type
        if table_type in MULTILINE_HEADER_PATTERNS:
            patterns = MULTILINE_HEADER_PATTERNS[table_type]
            # Try to find a pattern with matching column count
            matching_patterns = [p for p in patterns if len(p[0]) == len(column_headers)]
            if matching_patterns:
                pattern = rng.choice(matching_patterns)
                return list(pattern[0])  # Return the super-header row

        # Generate dynamic super-header based on semantic types
        super_header = []
        prev_semantic = None
        for i, spec in enumerate(template.column_specs):
            semantic = spec.semantic_type.value if hasattr(spec, 'semantic_type') else "OTHER"

            # Add category labels for groups of AMOUNT columns
            if semantic == "AMOUNT":
                if prev_semantic != "AMOUNT":
                    # Start of AMOUNT group - add category label
                    labels = ["Amounts", "Balance", "Financial", "Totals", "Values"]
                    super_header.append(rng.choice(labels))
                else:
                    super_header.append("")  # Continue group
            elif semantic == "DATE":
                super_header.append("Date" if prev_semantic != "DATE" else "")
            elif semantic == "VENDOR":
                super_header.append("")  # No super-header for vendor/name columns
            else:
                super_header.append("")

            prev_semantic = semantic

        # Only return if we have at least one non-empty label
        if any(super_header):
            return super_header
        return None

    def _should_generate_subtotal(self, template: 'TableTemplate', rng) -> bool:
        """
        Determine if this table should have a subtotal row.

        Only 30% of tables have subtotals (not forced on every page).
        """
        if not template.supports_subtotals:
            return False
        return rng.random() < 0.3

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

        # Set GL code format for this document (Phase5B enhancement)
        self._gl_code_format = rng.choice(GL_CODE_FORMATS)

        # Initialize document-level template state (Phase5A enhancement)
        # Use first table's title and extract building name from doc_id
        first_title = tables_data[0][1] if tables_data else "Report"
        building_name = doc_id.split("__")[0].replace("_", " ") if "__" in doc_id else first_title
        self._initialize_template_state(
            vendor_system=vendor_system,
            building_name=building_name,
            title=first_title,
            rng=rng
        )

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
        self._page_template_drawn = False  # Track if template header drawn on current page
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
            # Only if there's enough space on the page (need ~40pt for section header, ~30pt for note)
            min_space_needed = 50
            space_available = self.layout_engine.current_y - 15 - self.layout.margin_bottom
            if include_non_table_regions and i < len(tables_data) - 1 and rng.random() > 0.6 and space_available >= min_space_needed:
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
                # Signature block - needs about 60pt of space
                sig_height_needed = 60
                sig_start_y = self.layout_engine.current_y - 20
                # Only draw if there's enough space above margin
                if sig_start_y - sig_height_needed >= self.layout.margin_bottom:
                    sig_region, new_y = non_table_gen.generate_signature_block(
                        c=c,
                        doc_id=doc_id,
                        page_index=self.layout_engine.current_page,
                        style=self.vendor_style,
                        start_x=self.layout.content_start_x,
                        start_y=sig_start_y,
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
        data_rows, data_row_types = self._prepare_data_rows(template, transactions, rng)

        # Check for multi-line headers (40% chance - Phase5B enhancement)
        use_multiline = self._should_use_multiline_headers(template, rng)
        super_header_row = None
        if use_multiline:
            super_header_row = self._generate_multiline_header_row(template, column_headers, rng)

        # Build header rows list (1 or 2 rows)
        if super_header_row:
            header_rows = [super_header_row, column_headers]
            num_header_rows = 2
        else:
            header_rows = [column_headers]
            num_header_rows = 1

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
            self._page_template_drawn = False  # Reset template flag for new page

        table_id = f"{doc_id}__p{placement.page_index}_t{table_idx}"

        # Compute positions
        row_positions = self.layout_engine.compute_row_positions(
            placement, num_data_rows
        )

        # Combine header(s) + data for cell position calculation
        all_row_data = header_rows + data_rows

        cell_positions = self.layout_engine.compute_cell_positions(
            placement, row_positions, all_row_data
        )

        # Extract building name for TEMPLATE header
        building_name = doc_id.split("__")[0].replace("_", " ") if "__" in doc_id else title

        # Generate TEMPLATE header lines early (needed for drawing and metadata)
        total_pages_estimate = max(self.layout_engine.current_page + 1, 10)
        header_lines, footer_text = self._generate_template_text(
            page_num=placement.page_index + 1,
            total_pages=total_pages_estimate,
            company_name=building_name,
            rng=rng
        )

        # Save original start_y BEFORE any adjustments (for template header drawing)
        original_start_y = placement.start_y

        # Only draw template header ONCE per page (first table on page gets it)
        # Subsequent tables on the same page skip the header drawing AND offset
        should_draw_template = header_lines and not self._page_template_drawn

        # Compute header/footer positions ONCE using shared function
        # This ensures drawing and GT use IDENTICAL coordinates
        template_positions = None
        if should_draw_template:
            # Calculate template header height and adjust positions downward
            # This prevents headers from being cut off at the top of the page
            template_header_offset = self._get_template_header_height(header_lines, self.vendor_style)
            if template_header_offset > 0:
                # Adjust all Y positions downward (decrease Y since PDF Y=0 is bottom)
                # MUST adjust BOTH y_top AND y_bottom to maintain consistent coordinates
                for rp in row_positions:
                    rp.y_top -= template_header_offset
                    rp.y_bottom -= template_header_offset
                for cp in cell_positions:
                    cp.y_top -= template_header_offset
                    cp.y_bottom -= template_header_offset
                placement.start_y -= template_header_offset

            # Compute clamped positions for header/footer (SINGLE SOURCE OF TRUTH)
            table_bbox_for_positions = self.layout_engine.get_table_bbox(placement)
            template_positions = self._compute_header_footer_positions(
                placement_start_y=original_start_y,
                table_bbox=table_bbox_for_positions,
                header_lines=header_lines,
                footer_text=footer_text,
            )

            # Draw TEMPLATE header using pre-computed positions
            self._draw_template_header(
                c, header_lines,
                placement.start_x, original_start_y, placement.width,
                self.vendor_style,
                header_positions=template_positions,  # Use shared positions
            )
            self._page_template_drawn = True  # Mark that template header has been drawn
        elif not header_lines:
            # Only draw standalone title if no template header exists at all
            self._draw_title(c, placement, title, template)

        # Generate and render PAGE_HEADER (section title) - 70% of tables
        page_header_text = self._generate_page_header_text(template, building_name, rng)
        page_header_bbox = None

        if page_header_text:
            # Draw PAGE_HEADER between template header and column headers
            title_height = self.vendor_style.row_height * 1.5
            if should_draw_template:
                # Template header was drawn, occupying space from original_start_y downward
                # PAGE_HEADER goes just above column headers (which start at adjusted placement.start_y)
                # Use placement.start_y (already adjusted down) + small margin
                page_header_y = placement.start_y + 5
            else:
                # No template drawn on this page, PAGE_HEADER at top
                page_header_y = placement.start_y - title_height - 2
            page_header_bbox = self._draw_page_header_row(
                c, placement, page_header_text, page_header_y
            )

        # Render header row(s) - may be 1 or 2 rows for multi-line headers
        for header_idx in range(num_header_rows):
            header_cells = [cp for cp in cell_positions if cp.row_index == header_idx]
            self._draw_header_row(c, header_cells, template)

        # Render data rows (starting after header rows)
        for row_idx in range(num_header_rows, len(all_row_data)):
            row_cells = [cp for cp in cell_positions if cp.row_index == row_idx]
            data_row_idx = row_idx - num_header_rows  # Index into data_rows
            is_subtotal = self._is_subtotal_row(data_rows[data_row_idx])
            self._draw_data_row(c, row_cells, template, is_subtotal, row_index=row_idx)

        # Draw grid lines if enabled
        if template.has_grid_lines:
            self._draw_grid_lines(c, placement, row_positions, template)

        # Mark that we've drawn content to this page
        self._page_has_content = True

        # Build metadata
        rendered_rows: List[RenderedRow] = []

        # Add PAGE_HEADER as the first row if it exists
        row_offset = 0
        if page_header_text and page_header_bbox:
            page_header_row = RenderedRow(
                row_id=f"{table_id}_r0",
                table_id=table_id,
                page_index=placement.page_index,
                row_index=0,
                bbox=page_header_bbox,
                row_type=RowType.PAGE_HEADER,
                cells=[RenderedCell(
                    text=page_header_text,
                    page_index=placement.page_index,
                    row_index=0,
                    col_index=0,
                    bbox=page_header_bbox,
                    semantic_type=SemanticType.OTHER,
                    row_type=RowType.PAGE_HEADER,
                )],
            )
            rendered_rows.append(page_header_row)
            row_offset = 1

        # Prepend HEADER(s) to data_row_types to get full row_types list
        # For multi-line headers, we need multiple HEADER entries (one per header row)
        all_row_types = [RowType.HEADER] * num_header_rows + data_row_types

        for row_idx, row_pos in enumerate(row_positions):
            # Adjust row index to account for PAGE_HEADER row if present
            adjusted_row_idx = row_idx + row_offset
            row_id = f"{table_id}_r{adjusted_row_idx}"

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
                    row_index=adjusted_row_idx,
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
                row_index=adjusted_row_idx,
                bbox=row_bbox,
                row_type=row_type,
                cells=rendered_cells,
            ))

        table_bbox = self.layout_engine.get_table_bbox(placement)

        # Add TEMPLATE rows (Phase5A: multi-line headers + footer)
        # These are design layer elements that repeat IDENTICALLY on every page
        # GT coordinates come from template_positions (computed by _compute_header_footer_positions)
        # This ensures GT uses the EXACT SAME positions as drawing

        # Insert TEMPLATE rows at the very beginning (1-6 header lines)
        # Each line becomes a separate TEMPLATE row
        # Use positions from template_positions (computed before drawing)
        template_header_rows = []
        line_height = 15  # Height per header line

        if template_positions and template_positions.get("header_line_positions"):
            # Use pre-computed positions from shared function (SINGLE SOURCE OF TRUTH)
            header_line_positions = template_positions["header_line_positions"]

            for line_idx, header_line in enumerate(header_lines):
                if line_idx >= len(header_line_positions):
                    break

                y_baseline, y_top, y_bottom = header_line_positions[line_idx]
                header_bbox = (
                    placement.start_x,
                    y_bottom,  # ReportLab: y0 is bottom
                    placement.start_x + placement.width,
                    y_top,     # ReportLab: y1 is top
                )
                template_header_row = RenderedRow(
                    row_id=f"{table_id}_template_header_{line_idx}",
                    table_id=table_id,
                    page_index=placement.page_index,
                    row_index=-(len(header_lines) + 1) + line_idx,  # Negative indices before PAGE_HEADER
                    bbox=header_bbox,
                    row_type=RowType.TEMPLATE,
                    cells=[RenderedCell(
                        text=header_line,
                        page_index=placement.page_index,
                        row_index=-(len(header_lines) + 1) + line_idx,
                        col_index=0,
                        bbox=header_bbox,
                        semantic_type=SemanticType.OTHER,
                        row_type=RowType.TEMPLATE,
                    )],
                )
                template_header_rows.append(template_header_row)

        # Insert all header rows at the beginning
        for row in reversed(template_header_rows):
            rendered_rows.insert(0, row)

        # NOTE: Footer GT removed - footer_text is generated but never actually drawn
        # on the PDF canvas. Including GT for non-rendered content causes mismatches
        # when comparing GT to pdfplumber-extracted tokens.

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

        # Calculate maximum rows that fit on a page
        # Available content height: ~720pt (portrait)
        # Template header: ~80pt, PAGE_HEADER: ~30pt, column headers: ~20pt, padding: ~20pt
        # Available for data: ~570pt
        # With row_height ~14pt, max rows ~40
        max_rows = self._calculate_max_data_rows(template)

        # Limit data to max_rows
        limited_data = data[:max_rows]

        if isinstance(data[0], CashTransaction):
            return self._prepare_cash_rows(template, limited_data, rng)
        else:
            # For dict data, all rows are BODY except last which is SUBTOTAL if supported (30% chance)
            rows = self._prepare_dict_rows(template, limited_data)
            row_types = [RowType.BODY] * len(rows)
            if self._should_generate_subtotal(template, rng) and rows:
                row_types[-1] = RowType.SUBTOTAL_TOTAL
            return rows, row_types

    def _calculate_max_data_rows(self, template: TableTemplate) -> int:
        """Calculate maximum data rows that fit on a single page."""
        layout = self.layout_engine.layout
        available_height = layout.content_height

        # Reserve space for template header (conservative)
        available_height -= 85  # 4-line template header

        # Reserve space for PAGE_HEADER
        available_height -= template.row_height * 1.5 + 10

        # Reserve space for column headers (2 rows for multi-line)
        available_height -= template.row_height * 1.2 * 2

        # Reserve bottom padding
        available_height -= 25

        # Calculate max rows
        max_rows = int(available_height / template.row_height)

        # Ensure reasonable minimum and maximum
        return max(10, min(max_rows, 45))

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
                    row.append(self._format_gl_code(txn.gl_code))

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

        # Add subtotal row (30% of tables, not forced on every page)
        # Must use keyword from SUBTOTAL_KEYWORDS to be classified as SUBTOTAL_TOTAL
        if self._should_generate_subtotal(template, rng) and len(transactions) > 0:
            total_amount = sum(t.amount for t in transactions)
            subtotal_row = []
            # Choose a keyword for the subtotal
            keyword = rng.choice(["TOTAL", "SUBTOTAL", "GRAND TOTAL", "TOTALS"])
            for spec in template.column_specs:
                if spec.semantic_type == SemanticType.AMOUNT:
                    subtotal_row.append(f"{total_amount:,.2f}")
                elif spec.semantic_type == SemanticType.BALANCE:
                    subtotal_row.append(f"{running_balance:,.2f}")
                elif spec.semantic_type == SemanticType.VENDOR:
                    subtotal_row.append(keyword)
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

    def _draw_page_header_row(
        self,
        c: canvas.Canvas,
        placement: TablePlacement,
        page_header_text: str,
        y_position: float
    ) -> Tuple[float, float, float, float]:
        """
        Draw PAGE_HEADER row (section title like "Collection Status 245 East 72nd...").

        Args:
            c: Canvas to draw on
            placement: Table placement info
            page_header_text: The section title text
            y_position: Y position to draw at

        Returns:
            Bounding box (x0, y0, x1, y1) of the drawn row
        """
        style = self.vendor_style
        row_height = style.row_height * 1.2  # Slightly taller than normal row

        # Calculate positions
        x0 = placement.start_x
        x1 = placement.start_x + placement.width
        y1 = y_position
        y0 = y_position - row_height

        # Draw with bold font, slightly larger
        bold_font = get_bold_font(style.font_family)
        font_size = style.font_size + 1
        c.setFont(bold_font, font_size)
        c.setFillColor(black)

        text_y = y0 + 4
        c.drawString(x0 + style.cell_padding, text_y, page_header_text)

        return (x0, y0, x1, y1)

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

        elif style.grid_style == GridStyle.LINDENWOOD_TWO_SECTION:
            # For LINDENWOOD_TWO_SECTION, draw box around data table with column separators
            # (the two-section header is drawn separately with Unicode characters)
            # Outer box
            maybe_draw_line(placement.start_x, y_top, placement.start_x + placement.width, y_top, True)
            maybe_draw_line(placement.start_x, y_bottom, placement.start_x + placement.width, y_bottom, True)
            maybe_draw_line(placement.start_x, y_top, placement.start_x, y_bottom, True)
            maybe_draw_line(placement.start_x + placement.width, y_top, placement.start_x + placement.width, y_bottom, True)
            # Header separator
            maybe_draw_line(placement.start_x, header_y_bottom, placement.start_x + placement.width, header_y_bottom, True)
            # Vertical column separators (Lindenwood style has pipe separators)
            x = placement.start_x
            for i, width in enumerate(col_widths):
                if i > 0:  # Skip first to avoid double line at left edge
                    maybe_draw_line(x, y_top, x, y_bottom, False)
                x += width

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
            self._page_has_content = False
            self._page_template_drawn = False  # Reset template flag for new page

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
                ("GL Code:", self._format_gl_code(txn.gl_code), SemanticType.ACCOUNT),
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
        table_width = label_width + value_width

        # Add TEMPLATE rows (Phase5A: multi-line headers + footer)
        building_name = doc_id.split("__")[0].replace("_", " ") if "__" in doc_id else title
        self._add_template_rows(
            rendered_rows=rendered_rows,
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            building_name=building_name,
            placement_start_x=start_x,
            placement_start_y=start_y,
            placement_width=table_width,
            table_bbox=table_bbox,
            rng=rng
        )

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
                    self._format_gl_code(gl_code),
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
            self._page_has_content = False
            self._page_template_drawn = False  # Reset template flag for new page

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

        # Add TEMPLATE rows (Phase5A: multi-line headers + footer)
        building_name = doc_id.split("__")[0].replace("_", " ") if "__" in doc_id else title
        self._add_template_rows(
            rendered_rows=rendered_rows,
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            building_name=building_name,
            placement_start_x=start_x,
            placement_start_y=start_y,
            placement_width=table_width,
            table_bbox=table_bbox,
            rng=rng
        )

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
            self._page_has_content = False
            self._page_template_drawn = False  # Reset template flag for new page

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
                (self._format_gl_code(txn.gl_code), SemanticType.ACCOUNT),
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

        # Add TEMPLATE rows (Phase5A: multi-line headers + footer)
        building_name = doc_id.split("__")[0].replace("_", " ") if "__" in doc_id else title
        self._add_template_rows(
            rendered_rows=rendered_rows,
            table_id=table_id,
            page_index=self.layout_engine.current_page,
            building_name=building_name,
            placement_start_x=start_x,
            placement_start_y=start_y,
            placement_width=table_width,
            table_bbox=table_bbox,
            rng=rng
        )

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
