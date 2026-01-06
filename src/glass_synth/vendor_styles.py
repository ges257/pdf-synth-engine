"""Vendor visual style profiles for distinct PDF appearances."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple
from reportlab.lib.colors import Color, black, gray, lightgrey, white, HexColor


class GridStyle(Enum):
    """Grid line rendering styles."""
    FULL_GRID = "full_grid"           # All horizontal + vertical lines
    HORIZONTAL_ONLY = "horizontal"     # Only horizontal lines
    MINIMAL = "minimal"                # Just header/footer lines
    ALTERNATING_ROWS = "alternating"   # Zebra striping
    BOX_BORDERS = "box_borders"        # Outer border + header separator


@dataclass
class VendorStyle:
    """Visual style profile for a vendor system."""
    name: str
    font_family: str  # Base font name (Helvetica, Times-Roman, Courier)
    font_size: int
    header_font_size: int
    row_height: float
    grid_style: GridStyle
    grid_line_width: float
    grid_color: Color
    header_bg_color: Color
    header_text_color: Color
    alternating_row_color: Color  # Used when grid_style is ALTERNATING_ROWS
    cell_padding: float
    title_font_size: int
    compact_mode: bool  # Whether to use tighter spacing


# Define all 14 vendor styles per spec
VENDOR_STYLES: Dict[str, VendorStyle] = {
    "AKAM_OLD": VendorStyle(
        name="AKAM_OLD",
        font_family="Courier",
        font_size=8,
        header_font_size=9,
        row_height=12.0,
        grid_style=GridStyle.FULL_GRID,
        grid_line_width=0.75,
        grid_color=black,
        header_bg_color=HexColor("#D0D0D0"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=2.0,
        title_font_size=10,
        compact_mode=True,
    ),
    "AKAM_NEW": VendorStyle(
        name="AKAM_NEW",
        font_family="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.HORIZONTAL_ONLY,
        grid_line_width=0.5,
        grid_color=gray,
        header_bg_color=HexColor("#E8E8E8"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
    "DOUGLAS": VendorStyle(
        name="DOUGLAS",
        font_family="Times-Roman",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.BOX_BORDERS,
        grid_line_width=1.0,
        grid_color=black,
        header_bg_color=HexColor("#F0F0F0"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
    "FIRSTSERVICE": VendorStyle(
        name="FIRSTSERVICE",
        font_family="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=16.0,
        grid_style=GridStyle.ALTERNATING_ROWS,
        grid_line_width=0.5,
        grid_color=gray,
        header_bg_color=HexColor("#2C5282"),  # Dark blue
        header_text_color=white,
        alternating_row_color=HexColor("#F0F4F8"),
        cell_padding=4.0,
        title_font_size=14,
        compact_mode=False,
    ),
    "LINDENWOOD": VendorStyle(
        name="LINDENWOOD",
        font_family="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.MINIMAL,
        grid_line_width=0.5,
        grid_color=HexColor("#CCCCCC"),
        header_bg_color=white,
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
    "YARDI": VendorStyle(
        name="YARDI",
        font_family="Helvetica",
        font_size=8,
        header_font_size=9,
        row_height=12.0,
        grid_style=GridStyle.FULL_GRID,
        grid_line_width=0.5,
        grid_color=gray,
        header_bg_color=HexColor("#EEEEEE"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=2.0,
        title_font_size=10,
        compact_mode=True,
    ),
    "APPFOLIO": VendorStyle(
        name="APPFOLIO",
        font_family="Helvetica",
        font_size=10,
        header_font_size=11,
        row_height=16.0,
        grid_style=GridStyle.HORIZONTAL_ONLY,
        grid_line_width=0.25,
        grid_color=HexColor("#E0E0E0"),
        header_bg_color=white,
        header_text_color=HexColor("#333333"),
        alternating_row_color=white,
        cell_padding=4.0,
        title_font_size=14,
        compact_mode=False,
    ),
    "BUILDIUM": VendorStyle(
        name="BUILDIUM",
        font_family="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.ALTERNATING_ROWS,
        grid_line_width=0.5,
        grid_color=HexColor("#DDDDDD"),
        header_bg_color=HexColor("#4A5568"),  # Gray-blue
        header_text_color=white,
        alternating_row_color=HexColor("#F7FAFC"),
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
    "MDS": VendorStyle(
        name="MDS",
        font_family="Courier",
        font_size=8,
        header_font_size=9,
        row_height=11.0,
        grid_style=GridStyle.FULL_GRID,
        grid_line_width=0.5,
        grid_color=black,
        header_bg_color=HexColor("#CCCCCC"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=2.0,
        title_font_size=10,
        compact_mode=True,
    ),
    "CINC": VendorStyle(
        name="CINC",
        font_family="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.MINIMAL,
        grid_line_width=0.5,
        grid_color=HexColor("#B0B0B0"),
        header_bg_color=HexColor("#F5F5F5"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
    # OTHER vendors (4 variations)
    "OTHER_1": VendorStyle(
        name="OTHER_1",
        font_family="Times-Roman",
        font_size=10,
        header_font_size=11,
        row_height=15.0,
        grid_style=GridStyle.BOX_BORDERS,
        grid_line_width=0.75,
        grid_color=black,
        header_bg_color=HexColor("#E0E0E0"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=13,
        compact_mode=False,
    ),
    "OTHER_2": VendorStyle(
        name="OTHER_2",
        font_family="Courier",
        font_size=9,
        header_font_size=10,
        row_height=13.0,
        grid_style=GridStyle.HORIZONTAL_ONLY,
        grid_line_width=0.5,
        grid_color=gray,
        header_bg_color=lightgrey,
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=2.5,
        title_font_size=11,
        compact_mode=False,
    ),
    "OTHER_3": VendorStyle(
        name="OTHER_3",
        font_family="Helvetica",
        font_size=8,
        header_font_size=9,
        row_height=12.0,
        grid_style=GridStyle.ALTERNATING_ROWS,
        grid_line_width=0.25,
        grid_color=HexColor("#DDDDDD"),
        header_bg_color=HexColor("#3182CE"),  # Blue
        header_text_color=white,
        alternating_row_color=HexColor("#EBF8FF"),
        cell_padding=2.0,
        title_font_size=10,
        compact_mode=True,
    ),
    "OTHER_4": VendorStyle(
        name="OTHER_4",
        font_family="Times-Roman",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
        grid_style=GridStyle.FULL_GRID,
        grid_line_width=0.5,
        grid_color=HexColor("#999999"),
        header_bg_color=HexColor("#F0F0F0"),
        header_text_color=black,
        alternating_row_color=white,
        cell_padding=3.0,
        title_font_size=12,
        compact_mode=False,
    ),
}


def get_vendor_style(vendor_name: str) -> VendorStyle:
    """Get the visual style for a vendor, with fallback to OTHER style."""
    if vendor_name in VENDOR_STYLES:
        return VENDOR_STYLES[vendor_name]
    # Map "OTHER" to one of the OTHER variants
    if vendor_name == "OTHER":
        return VENDOR_STYLES["OTHER_1"]
    # Default fallback
    return VENDOR_STYLES["AKAM_NEW"]


def get_bold_font(font_family: str) -> str:
    """Get the bold variant of a font family."""
    if font_family == "Times-Roman":
        return "Times-Bold"
    elif font_family == "Courier":
        return "Courier-Bold"
    else:
        return f"{font_family}-Bold"
