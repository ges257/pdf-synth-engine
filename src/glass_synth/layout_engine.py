"""Layout engine for placing tables on PDF pages."""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from reportlab.lib.pagesizes import LETTER, landscape

from .table_templates import TableTemplate, TableType, LayoutType


# Page dimensions
PORTRAIT_SIZE = LETTER  # 612 x 792 points
LANDSCAPE_SIZE = landscape(LETTER)  # 792 x 612 points
DEFAULT_MARGIN = 36  # 0.5 inch margins


@dataclass
class PageLayout:
    """Defines the layout parameters for a page."""
    page_width: float = PORTRAIT_SIZE[0]
    page_height: float = PORTRAIT_SIZE[1]
    margin_left: float = DEFAULT_MARGIN
    margin_right: float = DEFAULT_MARGIN
    margin_top: float = DEFAULT_MARGIN
    margin_bottom: float = DEFAULT_MARGIN
    orientation: str = "portrait"  # "portrait" or "landscape"

    @classmethod
    def portrait(cls) -> "PageLayout":
        """Create a portrait layout."""
        return cls(
            page_width=PORTRAIT_SIZE[0],
            page_height=PORTRAIT_SIZE[1],
            orientation="portrait"
        )

    @classmethod
    def landscape(cls) -> "PageLayout":
        """Create a landscape layout."""
        return cls(
            page_width=LANDSCAPE_SIZE[0],
            page_height=LANDSCAPE_SIZE[1],
            orientation="landscape"
        )

    @property
    def content_width(self) -> float:
        return self.page_width - self.margin_left - self.margin_right

    @property
    def content_height(self) -> float:
        return self.page_height - self.margin_top - self.margin_bottom

    @property
    def content_start_x(self) -> float:
        return self.margin_left

    @property
    def content_start_y(self) -> float:
        """Top of content area (PDF coordinates start at bottom)."""
        return self.page_height - self.margin_top


@dataclass
class TablePlacement:
    """Describes where a table is placed on a page."""
    table_index: int
    page_index: int
    start_x: float
    start_y: float  # Top of table in PDF coordinates
    width: float
    height: float  # Computed after rendering
    template: TableTemplate
    title: str
    layout_type: LayoutType = LayoutType.HORIZONTAL_LEDGER
    is_split_right: bool = False  # For SPLIT_LEDGER: True if this is the right panel


@dataclass
class RowPlacement:
    """Describes where a row is placed within a table."""
    row_index: int
    y_top: float
    y_bottom: float
    row_height: float


@dataclass
class CellPlacement:
    """Describes where a cell is placed."""
    row_index: int
    col_index: int
    x: float
    y_top: float
    y_bottom: float
    width: float
    text: str


class LayoutEngine:
    """Engine for computing table and cell positions on pages."""

    def __init__(self, layout: Optional[PageLayout] = None):
        self.layout = layout or PageLayout()
        self.current_page = 0
        self.current_y = self.layout.content_start_y  # Start at top of content area

    def reset(self):
        """Reset layout state for a new document."""
        self.current_page = 0
        self.current_y = self.layout.content_start_y

    def compute_column_widths(
        self,
        template: TableTemplate,
        total_width: Optional[float] = None
    ) -> List[float]:
        """Compute absolute column widths from template ratios."""
        if total_width is None:
            total_width = self.layout.content_width

        widths = []
        for spec in template.column_specs:
            widths.append(spec.width_ratio * total_width)
        return widths

    def compute_table_height(
        self,
        template: TableTemplate,
        num_rows: int,
        include_title: bool = True,
        include_header: bool = True
    ) -> float:
        """Compute total table height including title, header, and data rows."""
        height = 0.0

        if include_title:
            height += template.row_height * 1.5  # Title row is taller

        if include_header:
            height += template.row_height * 1.2  # Header row slightly taller

        # Data rows
        height += num_rows * template.row_height

        # Add some padding
        height += 10  # Bottom padding

        return height

    def can_fit_on_current_page(self, height: float) -> bool:
        """Check if content of given height fits on current page."""
        return (self.current_y - height) >= self.layout.margin_bottom

    def start_new_page(self) -> int:
        """Move to a new page and return the new page index."""
        self.current_page += 1
        self.current_y = self.layout.content_start_y
        return self.current_page

    def place_table(
        self,
        template: TableTemplate,
        num_data_rows: int,
        title: str,
        table_index: int,
        layout_type: LayoutType = LayoutType.HORIZONTAL_LEDGER,
        is_split_right: bool = False
    ) -> TablePlacement:
        """
        Compute placement for a table.

        Returns TablePlacement with position info.
        May trigger a page break if needed.
        """
        # Calculate height needed
        table_height = self.compute_table_height(
            template,
            num_data_rows,
            include_title=True,
            include_header=True
        )

        # For SPLIT_LEDGER, tables are side-by-side so use half width
        if layout_type == LayoutType.SPLIT_LEDGER:
            table_width = (self.layout.content_width - 20) / 2  # 20pt gap between panels
        else:
            table_width = self.layout.content_width

        # Check if we need a new page (unless this is the right panel of a split)
        if not is_split_right and not self.can_fit_on_current_page(table_height):
            self.start_new_page()

        # Calculate start_x based on layout type
        if layout_type == LayoutType.SPLIT_LEDGER and is_split_right:
            start_x = self.layout.content_start_x + table_width + 20
        else:
            start_x = self.layout.content_start_x

        placement = TablePlacement(
            table_index=table_index,
            page_index=self.current_page,
            start_x=start_x,
            start_y=self.current_y,
            width=table_width,
            height=table_height,
            template=template,
            title=title,
            layout_type=layout_type,
            is_split_right=is_split_right,
        )

        # Update current Y position (move down) - only for non-split or right panel
        if layout_type != LayoutType.SPLIT_LEDGER or is_split_right:
            self.current_y -= table_height + 20  # 20pt gap between tables

        return placement

    def compute_row_positions(
        self,
        placement: TablePlacement,
        num_data_rows: int,
        include_title: bool = True,
        include_header: bool = True
    ) -> List[RowPlacement]:
        """
        Compute Y positions for all rows in a table.

        Returns list of RowPlacement objects.
        Row index 0 = header (if included), subsequent = data rows.
        """
        template = placement.template
        positions = []
        y = placement.start_y

        row_idx = 0

        # Title row
        if include_title:
            title_height = template.row_height * 1.5
            y -= title_height
            # Title is not counted as a row for labeling purposes

        # Header row
        if include_header:
            header_height = template.row_height * 1.2
            y_top = y
            y -= header_height
            positions.append(RowPlacement(
                row_index=row_idx,
                y_top=y_top,
                y_bottom=y,
                row_height=header_height,
            ))
            row_idx += 1

        # Data rows
        for _ in range(num_data_rows):
            y_top = y
            y -= template.row_height
            positions.append(RowPlacement(
                row_index=row_idx,
                y_top=y_top,
                y_bottom=y,
                row_height=template.row_height,
            ))
            row_idx += 1

        return positions

    def compute_cell_positions(
        self,
        placement: TablePlacement,
        row_positions: List[RowPlacement],
        row_data: List[List[str]]  # List of rows, each row is list of cell texts
    ) -> List[CellPlacement]:
        """
        Compute positions for all cells in a table.

        Returns list of CellPlacement objects with bbox info.
        """
        template = placement.template
        col_widths = self.compute_column_widths(template, placement.width)

        cells = []

        for row_idx, (row_pos, row_texts) in enumerate(zip(row_positions, row_data)):
            x = placement.start_x

            for col_idx, (text, width) in enumerate(zip(row_texts, col_widths)):
                cells.append(CellPlacement(
                    row_index=row_idx,
                    col_index=col_idx,
                    x=x,
                    y_top=row_pos.y_top,
                    y_bottom=row_pos.y_bottom,
                    width=width,
                    text=text,
                ))
                x += width

        return cells

    def get_cell_bbox(self, cell: CellPlacement) -> Tuple[float, float, float, float]:
        """Get bounding box for a cell as (x0, y0, x1, y1)."""
        return (
            cell.x,
            cell.y_bottom,
            cell.x + cell.width,
            cell.y_top,
        )

    def get_row_bbox(
        self,
        placement: TablePlacement,
        row_pos: RowPlacement
    ) -> Tuple[float, float, float, float]:
        """Get bounding box for a row as (x0, y0, x1, y1)."""
        return (
            placement.start_x,
            row_pos.y_bottom,
            placement.start_x + placement.width,
            row_pos.y_top,
        )

    def get_table_bbox(
        self,
        placement: TablePlacement
    ) -> Tuple[float, float, float, float]:
        """Get bounding box for entire table as (x0, y0, x1, y1)."""
        return (
            placement.start_x,
            placement.start_y - placement.height,
            placement.start_x + placement.width,
            placement.start_y,
        )
