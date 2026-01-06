"""Generate NON_TABLE regions for Model 1 training."""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from faker import Faker
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, gray

from .vendor_styles import VendorStyle, get_bold_font


@dataclass
class NonTableRegion:
    """Represents a non-table region for Model 1 training."""
    region_id: str
    doc_id: str
    page_index: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    region_type: str  # "HEADER", "FOOTER", "NOTE", "SECTION_HEADER", "SIGNATURE", "WHITESPACE"
    text: str
    is_table_region: bool = False  # Always False for NON_TABLE


class NonTableGenerator:
    """Generate non-table regions in PDFs."""

    def __init__(self, fake: Optional[Faker] = None):
        self.fake = fake or Faker()

    def generate_document_header(
        self,
        c: canvas.Canvas,
        doc_id: str,
        page_index: int,
        style: VendorStyle,
        start_x: float,
        start_y: float,
        width: float,
        rng: np.random.Generator,
    ) -> NonTableRegion:
        """Generate a document header with property/company info."""
        region_id = f"{doc_id}__p{page_index}_header"

        # Generate property/company name
        property_names = [
            f"{self.fake.city()} Condominium Association",
            f"{self.fake.city()} Homeowners Association",
            f"The {self.fake.last_name()} at {self.fake.city()}",
            f"{rng.integers(100, 999)} {self.fake.street_name()} Condo",
            f"{self.fake.company()} Management Co.",
        ]
        property_name = rng.choice(property_names)

        # Address line
        address = f"{self.fake.street_address()}, {self.fake.city()}, {self.fake.state_abbr()} {self.fake.zipcode()}"

        # Draw header
        bold_font = get_bold_font(style.font_family)
        y = start_y

        # Property name (bold, larger)
        c.setFont(bold_font, style.header_font_size + 2)
        c.setFillColor(black)
        c.drawString(start_x, y, property_name)
        y -= style.row_height * 1.3

        # Address (regular)
        c.setFont(style.font_family, style.font_size)
        c.drawString(start_x, y, address)
        y -= style.row_height * 1.5

        # Calculate bbox
        header_height = start_y - y
        bbox = (start_x, y, start_x + width, start_y)

        text = f"{property_name}\n{address}"

        return NonTableRegion(
            region_id=region_id,
            doc_id=doc_id,
            page_index=page_index,
            bbox=bbox,
            region_type="HEADER",
            text=text,
        ), y

    def generate_page_footer(
        self,
        c: canvas.Canvas,
        doc_id: str,
        page_index: int,
        page_number: int,
        total_pages: int,
        style: VendorStyle,
        start_x: float,
        bottom_y: float,
        width: float,
        rng: np.random.Generator,
    ) -> NonTableRegion:
        """Generate a page footer with page number and/or notice."""
        region_id = f"{doc_id}__p{page_index}_footer"

        # Footer text options
        footer_texts = [
            f"Page {page_number} of {total_pages}",
            f"Page {page_number}",
            f"- {page_number} -",
            "CONFIDENTIAL - For Owner Use Only",
            "This report is computer generated. Please contact management with questions.",
        ]
        footer_text = rng.choice(footer_texts)

        # Draw footer
        c.setFont(style.font_family, style.font_size - 1)
        c.setFillColor(gray)
        y = bottom_y + 10

        # Center the text
        text_width = c.stringWidth(footer_text, style.font_family, style.font_size - 1)
        text_x = start_x + (width - text_width) / 2
        c.drawString(text_x, y, footer_text)

        # Calculate bbox
        bbox = (start_x, bottom_y, start_x + width, bottom_y + 25)

        return NonTableRegion(
            region_id=region_id,
            doc_id=doc_id,
            page_index=page_index,
            bbox=bbox,
            region_type="FOOTER",
            text=footer_text,
        )

    def generate_section_header(
        self,
        c: canvas.Canvas,
        doc_id: str,
        page_index: int,
        section_idx: int,
        style: VendorStyle,
        start_x: float,
        start_y: float,
        width: float,
        rng: np.random.Generator,
        period_text: str = "March 2025",
    ) -> NonTableRegion:
        """Generate a section header between tables."""
        region_id = f"{doc_id}__p{page_index}_section{section_idx}"

        # Section header texts
        section_texts = [
            f"Financial Summary - {period_text}",
            f"Statement Period: {period_text}",
            f"Report Date: {self.fake.date_this_month().strftime('%B %d, %Y')}",
            "Operating Fund Report",
            "Reserve Fund Activity",
            f"For the Month Ending {period_text}",
        ]
        section_text = rng.choice(section_texts)

        # Draw section header
        bold_font = get_bold_font(style.font_family)
        c.setFont(bold_font, style.font_size + 1)
        c.setFillColor(black)
        y = start_y

        c.drawString(start_x, y, section_text)

        # Add underline for some styles
        if rng.random() > 0.5:
            c.setStrokeColor(gray)
            c.setLineWidth(0.5)
            text_width = c.stringWidth(section_text, bold_font, style.font_size + 1)
            c.line(start_x, y - 2, start_x + text_width, y - 2)

        y -= style.row_height * 1.2

        # Calculate bbox
        bbox = (start_x, y, start_x + width * 0.6, start_y + style.row_height)

        return NonTableRegion(
            region_id=region_id,
            doc_id=doc_id,
            page_index=page_index,
            bbox=bbox,
            region_type="SECTION_HEADER",
            text=section_text,
        ), y

    def generate_note_block(
        self,
        c: canvas.Canvas,
        doc_id: str,
        page_index: int,
        note_idx: int,
        style: VendorStyle,
        start_x: float,
        start_y: float,
        width: float,
        rng: np.random.Generator,
    ) -> NonTableRegion:
        """Generate a note or disclaimer text block."""
        region_id = f"{doc_id}__p{page_index}_note{note_idx}"

        # Note texts
        notes = [
            "Note: All figures are unaudited and subject to change.",
            "* Denotes estimated amounts pending final invoice.",
            "See attached schedule for detailed reserve fund analysis.",
            "Questions? Contact your property manager at the number listed above.",
            "This report was prepared using data as of the last business day of the month.",
            "Amounts may not sum due to rounding.",
            "Year-to-date figures include prior period adjustments.",
        ]
        note_text = rng.choice(notes)

        # Draw note
        c.setFont(style.font_family, style.font_size - 1)
        c.setFillColor(gray)
        y = start_y

        # Wrap long text
        max_width = width * 0.8
        if c.stringWidth(note_text, style.font_family, style.font_size - 1) > max_width:
            # Simple word wrap
            words = note_text.split()
            lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                if c.stringWidth(test_line, style.font_family, style.font_size - 1) > max_width:
                    if current_line:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)
                        current_line = []
                else:
                    current_line.append(word)
            if current_line:
                lines.append(' '.join(current_line))

            for line in lines:
                c.drawString(start_x, y, line)
                y -= style.row_height * 0.9
        else:
            c.drawString(start_x, y, note_text)
            y -= style.row_height

        y -= style.row_height * 0.3  # Extra padding

        # Calculate bbox
        bbox = (start_x, y, start_x + max_width, start_y + style.row_height)

        return NonTableRegion(
            region_id=region_id,
            doc_id=doc_id,
            page_index=page_index,
            bbox=bbox,
            region_type="NOTE",
            text=note_text,
        ), y

    def generate_signature_block(
        self,
        c: canvas.Canvas,
        doc_id: str,
        page_index: int,
        style: VendorStyle,
        start_x: float,
        start_y: float,
        width: float,
        rng: np.random.Generator,
    ) -> NonTableRegion:
        """Generate a signature block (typically at end of document)."""
        region_id = f"{doc_id}__p{page_index}_signature"

        # Signature block components
        titles = ["Prepared by:", "Reviewed by:", "Approved by:", "Property Manager:"]
        title = rng.choice(titles)
        name = self.fake.name()
        date_str = self.fake.date_this_month().strftime("%m/%d/%Y")

        y = start_y

        # Draw signature block
        c.setFont(style.font_family, style.font_size)
        c.setFillColor(black)

        c.drawString(start_x, y, title)
        y -= style.row_height * 1.5

        # Signature line
        c.setStrokeColor(black)
        c.setLineWidth(0.5)
        line_width = 150
        c.line(start_x, y, start_x + line_width, y)
        y -= style.row_height * 0.3

        c.setFont(style.font_family, style.font_size - 1)
        c.drawString(start_x, y, name)
        y -= style.row_height

        c.drawString(start_x, y, f"Date: {date_str}")
        y -= style.row_height

        # Calculate bbox
        bbox = (start_x, y, start_x + line_width + 50, start_y + style.row_height)

        text = f"{title}\n{name}\nDate: {date_str}"

        return NonTableRegion(
            region_id=region_id,
            doc_id=doc_id,
            page_index=page_index,
            bbox=bbox,
            region_type="SIGNATURE",
            text=text,
        ), y


def non_table_to_model1_label(region: NonTableRegion) -> dict:
    """Convert NonTableRegion to Model 1 label format."""
    return {
        "region_id": region.region_id,
        "doc_id": region.doc_id,
        "page_index": region.page_index,
        "bbox": list(region.bbox),
        "table_type": "NON_TABLE",
        "layout_type": "none",
        "is_table_region": False,
        "vendor_system": "N/A",
        "title_text": "",
        "fund": "",
        "n_rows": 0,
        "n_cols": 0,
        "column_headers": [],
        "orientation": "portrait",
        "region_type": region.region_type,
        "text_content": region.text,
    }
