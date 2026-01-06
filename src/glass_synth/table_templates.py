"""Table templates and column specifications for different vendor styles."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple


class TableType(Enum):
    """Types of tables in CIRA financial statements."""
    CASH_OUT = "CASH_OUT"  # Cash disbursements / Schedule B
    CASH_IN = "CASH_IN"    # Cash receipts / Schedule D
    BUDGET = "BUDGET"      # Budget vs Actual / Income Statement
    UNPAID = "UNPAID"      # Unpaid Bills / Open Payables
    AGING = "AGING"        # Aging / Arrears
    GL = "GL"              # General Ledger
    OTHER = "OTHER"        # Misc tables
    NON_TABLE = "NON_TABLE"  # Non-table regions


class LayoutType(Enum):
    """Layout geometry variants for tables (Appendix C)."""
    HORIZONTAL_LEDGER = "horizontal_ledger"    # Classic row-based tables (55%)
    SPLIT_LEDGER = "split_ledger"              # Two horizontal tables side-by-side (10%)
    VERTICAL_KV = "vertical_key_value"         # Label/value stacked form (10%)
    MATRIX = "matrix_budget"                   # GL x period cross-tab (15%)
    RAGGED = "ragged_pseudotable"              # Misaligned/semi-structured (10%)


class SemanticType(Enum):
    """Semantic types for token classification (Model 3)."""
    # Original 5 types
    DATE = "DATE"
    VENDOR = "VENDOR"
    ACCOUNT = "ACCOUNT"  # GL code or account name
    AMOUNT = "AMOUNT"
    OTHER = "OTHER"
    # New semantic types for enhanced coverage
    INVOICE_NUMBER = "INVOICE_NUMBER"  # Invoice identifiers (INV-12345)
    CHECK_NUMBER = "CHECK_NUMBER"      # Check/payment reference numbers
    BALANCE = "BALANCE"                # Running or opening balance amounts
    STATUS = "STATUS"                  # Payment/account status (Paid, Open, Pending)
    VENDOR_CODE = "VENDOR_CODE"        # 4-character vendor identifiers
    UNIT_CODE = "UNIT_CODE"            # Unit/apartment identifiers
    CHARGE_TYPE = "CHARGE_TYPE"        # Charge category labels (Base, Shares, Fees)


class RowType(Enum):
    """Row types for row classification (Model 2)."""
    TEMPLATE = "TEMPLATE"           # Design layer (company name, page numbers) - removed before Model 2
    PAGE_HEADER = "PAGE_HEADER"     # Section/report title ("Collection Status 245 East...")
    HEADER = "HEADER"               # Column headers (can be multi-line)
    BODY = "BODY"                   # Transaction data rows
    SUBTOTAL_TOTAL = "SUBTOTAL_TOTAL"  # Actual totals with keywords
    NOTE = "NOTE"                   # Footnotes, annotations


@dataclass
class ColumnSpec:
    """Specification for a table column."""
    name: str  # Header label
    semantic_type: SemanticType
    width_ratio: float  # Relative width (fractions that sum to 1.0)
    alignment: str = "left"  # "left", "center", "right"


@dataclass
class TableTemplate:
    """Template for a specific table type and vendor style."""
    vendor_system: str
    table_type: TableType
    title_options: List[str]
    column_specs: List[ColumnSpec]
    supports_subtotals: bool = True
    typical_row_count_range: Tuple[int, int] = (10, 50)
    has_grid_lines: bool = True
    font_name: str = "Helvetica"
    font_size: int = 9
    header_font_size: int = 10
    row_height: float = 14.0


# Column name synonyms per spec Section 3.3
DATE_SYNONYMS = ["Date", "Trans Date", "Transaction Date", "Posting Date", "Post Date"]
VENDOR_SYNONYMS = ["Vendor", "Payee", "Paid To", "Name", "Description"]
CHECK_SYNONYMS = ["Check #", "Check No", "Chk #", "Reference", "Ref #", "CK NO"]
AMOUNT_SYNONYMS = ["Amount", "Paid", "Total", "Payment", "Total Amount"]
GL_CODE_SYNONYMS = ["GL Code", "Account #", "Acct #", "GL #", "Account", "G/L"]
DESCRIPTION_SYNONYMS = ["Description", "Memo", "Notes", "Detail", "Expense Type"]

# Extended synonyms for new semantic types
INVOICE_SYNONYMS = ["Invoice #", "Inv #", "Invoice No", "INV", "Invoice Number", "Invoice"]
VENDOR_CODE_SYNONYMS = ["VEND", "Vendor Code", "V/C", "VCode", "Vnd"]
PO_SYNONYMS = ["P/O", "PO #", "Purchase Order", "P.O.", "PO No"]
REMARKS_SYNONYMS = ["Remarks", "Notes", "Comments", "Memo", "Remarks/Notes"]
PAYEE_SYNONYMS = ["Paid To", "Payee Name", "Payee", "Pay To"]
UNIT_SYNONYMS = ["Unit", "Apt", "Unit #", "Apartment", "Suite", "Unit ID"]
TENANT_CODE_SYNONYMS = ["Account", "Tenant Code", "Acct", "Tenant ID", "Account Code", "Acct No"]
OPENING_BAL_SYNONYMS = ["Opening Balance", "Open Bal", "Beg Balance", "Beginning Bal", "Prior Bal"]
CLOSING_BAL_SYNONYMS = ["Closing Balance", "Close Bal", "End Balance", "Ending Bal", "Balance"]
BASE_CHARGE_SYNONYMS = ["Base Charge", "Base Rent", "Maint Fee", "HOA Fee", "Base", "Maintenance"]
SHARES_SYNONYMS = ["Shares", "Share Amt", "Co-op Shares", "Ownership %", "Shrs"]
STATUS_SYNONYMS = ["Status", "Paid Status", "State", "Payment Status", "Pmt Status"]
RECEIPT_SYNONYMS = ["Receipt #", "Rcpt #", "Receipt No", "Deposit #", "Ref #"]
CHECK_DATE_SYNONYMS = ["Check Date", "Chk Date", "Payment Date", "Paid Date"]
INVOICE_DATE_SYNONYMS = ["Invoice Date", "Inv Date", "Bill Date", "Date"]


def get_cash_out_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """
    Get a CASH_OUT (disbursements) template for a vendor.

    Enhanced with INVOICE #, Invoice Date, Check Date, Vendor Code, P/O, Remarks.
    """
    if vendor == "AKAM_NEW":
        # Full template with all columns (0.07+0.06+0.04+0.13+0.08+0.05+0.07+0.13+0.06+0.11+0.10+0.10 = 1.0)
        return TableTemplate(
            vendor_system="AKAM_NEW",
            table_type=TableType.CASH_OUT,
            title_options=[
                "Schedule B - Statement of Paid Bills",
                "Cash Disbursements",
                "Paid Items",
                "Check Register",
                "Disbursement Journal",
            ],
            column_specs=[
                ColumnSpec("Invoice Date", SemanticType.DATE, 0.07, "left"),
                ColumnSpec("Check Date", SemanticType.DATE, 0.06, "left"),
                ColumnSpec("VEND", SemanticType.VENDOR_CODE, 0.04, "center"),
                ColumnSpec("Vendor", SemanticType.VENDOR, 0.13, "left"),
                ColumnSpec("Invoice #", SemanticType.INVOICE_NUMBER, 0.08, "left"),
                ColumnSpec("P/O", SemanticType.OTHER, 0.05, "center"),
                ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.07, "left"),
                ColumnSpec("Description", SemanticType.OTHER, 0.13, "left"),
                ColumnSpec("Check #", SemanticType.CHECK_NUMBER, 0.06, "center"),
                ColumnSpec("Amount", SemanticType.AMOUNT, 0.11, "right"),
                ColumnSpec("Balance", SemanticType.BALANCE, 0.10, "right"),
                ColumnSpec("Remarks", SemanticType.OTHER, 0.10, "left"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(15, 60),
            has_grid_lines=True,
            font_name="Helvetica",
            font_size=8,  # Smaller to fit more columns
            header_font_size=9,
            row_height=13.0,
        )
    elif vendor in ["AKAM_OLD", "MDS", "LINDENWOOD"]:
        # Compact Lindenwood-style (0.07+0.06+0.04+0.14+0.08+0.08+0.10+0.06+0.12+0.10+0.15 = 1.0)
        return TableTemplate(
            vendor_system=vendor,
            table_type=TableType.CASH_OUT,
            title_options=[
                "Statement of Disbursements",
                "Schedule B - Statement of Paid Bills",
                "Check Register",
            ],
            column_specs=[
                ColumnSpec("Date", SemanticType.DATE, 0.07, "left"),
                ColumnSpec("CK NO", SemanticType.CHECK_NUMBER, 0.06, "center"),
                ColumnSpec("VEND", SemanticType.VENDOR_CODE, 0.04, "center"),
                ColumnSpec("Paid To", SemanticType.VENDOR, 0.14, "left"),
                ColumnSpec("Invoice #", SemanticType.INVOICE_NUMBER, 0.08, "left"),
                ColumnSpec("P/O", SemanticType.OTHER, 0.08, "center"),
                ColumnSpec("G/L", SemanticType.ACCOUNT, 0.10, "left"),
                ColumnSpec("Expense Type", SemanticType.OTHER, 0.06, "left"),
                ColumnSpec("Amount", SemanticType.AMOUNT, 0.12, "right"),
                ColumnSpec("Balance", SemanticType.BALANCE, 0.10, "right"),
                ColumnSpec("Remarks", SemanticType.OTHER, 0.15, "left"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(20, 80),
            has_grid_lines=True,
            font_name="Courier",
            font_size=8,
            header_font_size=9,
            row_height=12.0,
        )
    else:
        # Default template for other vendors (0.08+0.07+0.16+0.09+0.09+0.14+0.07+0.12+0.10+0.08 = 1.0)
        return TableTemplate(
            vendor_system=vendor,
            table_type=TableType.CASH_OUT,
            title_options=[
                "Cash Disbursements",
                "Check Register",
                "Payment Register",
            ],
            column_specs=[
                ColumnSpec("Date", SemanticType.DATE, 0.08, "left"),
                ColumnSpec("Check #", SemanticType.CHECK_NUMBER, 0.07, "center"),
                ColumnSpec("Vendor", SemanticType.VENDOR, 0.16, "left"),
                ColumnSpec("Invoice #", SemanticType.INVOICE_NUMBER, 0.09, "left"),
                ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.09, "left"),
                ColumnSpec("Description", SemanticType.OTHER, 0.14, "left"),
                ColumnSpec("P/O", SemanticType.OTHER, 0.07, "center"),
                ColumnSpec("Amount", SemanticType.AMOUNT, 0.12, "right"),
                ColumnSpec("Balance", SemanticType.BALANCE, 0.10, "right"),
                ColumnSpec("Remarks", SemanticType.OTHER, 0.08, "left"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(15, 60),
            has_grid_lines=True,
            font_name="Helvetica",
            font_size=9,
            header_font_size=10,
            row_height=14.0,
        )


def get_cash_in_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """
    Get a CASH_IN (receipts) template for a vendor.

    Enhanced with Account Code, Opening Balance, Base Charge, Shares, Status.
    """
    if vendor == "AKAM_NEW":
        # Full template (0.06+0.06+0.04+0.12+0.08+0.08+0.08+0.10+0.06+0.10+0.10+0.06+0.06 = 1.0)
        return TableTemplate(
            vendor_system="AKAM_NEW",
            table_type=TableType.CASH_IN,
            title_options=[
                "Schedule D - Collection Status",
                "Cash Receipts",
                "Deposits",
                "Revenue Receipts",
                "Collection Report",
            ],
            column_specs=[
                ColumnSpec("Date", SemanticType.DATE, 0.06, "left"),
                ColumnSpec("Acct No", SemanticType.UNIT_CODE, 0.06, "left"),
                ColumnSpec("Unit", SemanticType.UNIT_CODE, 0.04, "center"),
                ColumnSpec("Owner", SemanticType.VENDOR, 0.12, "left"),
                ColumnSpec("Open Bal", SemanticType.BALANCE, 0.08, "right"),
                ColumnSpec("Base Charge", SemanticType.AMOUNT, 0.08, "right"),
                ColumnSpec("Shares", SemanticType.AMOUNT, 0.08, "right"),
                ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.10, "left"),
                ColumnSpec("Receipt #", SemanticType.CHECK_NUMBER, 0.06, "center"),
                ColumnSpec("Amount", SemanticType.AMOUNT, 0.10, "right"),
                ColumnSpec("Balance", SemanticType.BALANCE, 0.10, "right"),
                ColumnSpec("Status", SemanticType.STATUS, 0.06, "center"),
                ColumnSpec("Description", SemanticType.OTHER, 0.06, "left"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(10, 40),
            has_grid_lines=True,
            font_name="Helvetica",
            font_size=8,
            header_font_size=9,
            row_height=13.0,
        )
    elif vendor in ["COOP", "LINDENWOOD"]:
        # Co-op / Lindenwood style (0.06+0.06+0.05+0.14+0.06+0.09+0.09+0.06+0.11+0.11+0.09+0.08 = 1.0)
        return TableTemplate(
            vendor_system=vendor,
            table_type=TableType.CASH_IN,
            title_options=[
                "Collection Status",
                "Shareholder Receipts",
                "Maintenance Collection",
                "Schedule D - Collection Status",
            ],
            column_specs=[
                ColumnSpec("Date", SemanticType.DATE, 0.06, "left"),
                ColumnSpec("Acct", SemanticType.UNIT_CODE, 0.06, "left"),
                ColumnSpec("Apt", SemanticType.UNIT_CODE, 0.05, "center"),
                ColumnSpec("Resident", SemanticType.VENDOR, 0.14, "left"),
                ColumnSpec("Shares", SemanticType.AMOUNT, 0.06, "right"),
                ColumnSpec("Open Bal", SemanticType.BALANCE, 0.09, "right"),
                ColumnSpec("Base Charge", SemanticType.AMOUNT, 0.09, "right"),
                ColumnSpec("Receipt #", SemanticType.CHECK_NUMBER, 0.06, "center"),
                ColumnSpec("Paid", SemanticType.AMOUNT, 0.11, "right"),
                ColumnSpec("Close Bal", SemanticType.BALANCE, 0.11, "right"),
                ColumnSpec("Status", SemanticType.STATUS, 0.09, "center"),
                ColumnSpec("Charges", SemanticType.OTHER, 0.08, "left"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(10, 50),
            has_grid_lines=True,
            font_name="Helvetica",
            font_size=8,
            header_font_size=9,
            row_height=13.0,
        )
    else:
        # Default template (0.07+0.05+0.05+0.14+0.09+0.09+0.10+0.07+0.12+0.12+0.10 = 1.0)
        return TableTemplate(
            vendor_system=vendor,
            table_type=TableType.CASH_IN,
            title_options=[
                "Cash Receipts",
                "Deposits",
                "Collection Report",
            ],
            column_specs=[
                ColumnSpec("Date", SemanticType.DATE, 0.07, "left"),
                ColumnSpec("Acct", SemanticType.UNIT_CODE, 0.05, "left"),
                ColumnSpec("Unit", SemanticType.UNIT_CODE, 0.05, "center"),
                ColumnSpec("Owner", SemanticType.VENDOR, 0.14, "left"),
                ColumnSpec("Open Bal", SemanticType.BALANCE, 0.09, "right"),
                ColumnSpec("Base Charge", SemanticType.AMOUNT, 0.09, "right"),
                ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.10, "left"),
                ColumnSpec("Receipt #", SemanticType.CHECK_NUMBER, 0.07, "center"),
                ColumnSpec("Amount", SemanticType.AMOUNT, 0.12, "right"),
                ColumnSpec("Balance", SemanticType.BALANCE, 0.12, "right"),
                ColumnSpec("Status", SemanticType.STATUS, 0.10, "center"),
            ],
            supports_subtotals=True,
            typical_row_count_range=(10, 40),
            has_grid_lines=True,
            font_name="Helvetica",
            font_size=9,
            header_font_size=10,
            row_height=14.0,
        )


def get_budget_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """Get a BUDGET (Income Statement / Budget vs Actual) template."""
    return TableTemplate(
        vendor_system=vendor,
        table_type=TableType.BUDGET,
        title_options=[
            "Income Statement",
            "Budget vs Actual",
            "Statement of Revenue and Expenses",
            "Operating Budget Comparison",
            "Financial Summary",
        ],
        column_specs=[
            ColumnSpec("Account", SemanticType.ACCOUNT, 0.30, "left"),
            ColumnSpec("Current", SemanticType.AMOUNT, 0.14, "right"),
            ColumnSpec("YTD Actual", SemanticType.AMOUNT, 0.14, "right"),
            ColumnSpec("YTD Budget", SemanticType.AMOUNT, 0.14, "right"),
            ColumnSpec("Annual Budget", SemanticType.AMOUNT, 0.14, "right"),
            ColumnSpec("Variance", SemanticType.AMOUNT, 0.14, "right"),
        ],
        supports_subtotals=True,
        typical_row_count_range=(20, 80),
        has_grid_lines=True,
        font_name="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
    )


def get_unpaid_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """Get an UNPAID (Open Payables / Unpaid Bills) template."""
    return TableTemplate(
        vendor_system=vendor,
        table_type=TableType.UNPAID,
        title_options=[
            "Unpaid Bills",
            "Open Payables",
            "Accounts Payable Aging",
            "Outstanding Invoices",
            "Bills Due",
        ],
        column_specs=[
            ColumnSpec("Date", SemanticType.DATE, 0.10, "left"),
            ColumnSpec("Vendor", SemanticType.VENDOR, 0.22, "left"),
            ColumnSpec("Invoice #", SemanticType.INVOICE_NUMBER, 0.10, "left"),
            ColumnSpec("Due Date", SemanticType.DATE, 0.10, "left"),
            ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.12, "left"),
            ColumnSpec("Description", SemanticType.OTHER, 0.18, "left"),
            ColumnSpec("Amount", SemanticType.AMOUNT, 0.18, "right"),
        ],
        supports_subtotals=True,
        typical_row_count_range=(10, 40),
        has_grid_lines=True,
        font_name="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
    )


def get_aging_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """Get an AGING (Receivables Aging / Arrears) template."""
    return TableTemplate(
        vendor_system=vendor,
        table_type=TableType.AGING,
        title_options=[
            "Aged Receivables",
            "Arrears Report",
            "Collection Status by Age",
            "Receivables Aging Summary",
            "Owner Aging Report",
        ],
        column_specs=[
            ColumnSpec("Unit", SemanticType.VENDOR, 0.08, "left"),
            ColumnSpec("Owner", SemanticType.VENDOR, 0.18, "left"),
            ColumnSpec("Current", SemanticType.AMOUNT, 0.12, "right"),
            ColumnSpec("30 Days", SemanticType.AMOUNT, 0.12, "right"),
            ColumnSpec("60 Days", SemanticType.AMOUNT, 0.12, "right"),
            ColumnSpec("90 Days", SemanticType.AMOUNT, 0.12, "right"),
            ColumnSpec("90+ Days", SemanticType.AMOUNT, 0.12, "right"),
            ColumnSpec("Total", SemanticType.AMOUNT, 0.14, "right"),
        ],
        supports_subtotals=True,
        typical_row_count_range=(15, 60),
        has_grid_lines=True,
        font_name="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
    )


def get_gl_template(vendor: str = "AKAM_NEW") -> TableTemplate:
    """Get a GL (General Ledger) template."""
    return TableTemplate(
        vendor_system=vendor,
        table_type=TableType.GL,
        title_options=[
            "General Ledger",
            "GL Detail",
            "Account Activity",
            "Transaction Detail",
            "Ledger Activity Report",
        ],
        column_specs=[
            ColumnSpec("Date", SemanticType.DATE, 0.10, "left"),
            ColumnSpec("Reference", SemanticType.CHECK_NUMBER, 0.10, "left"),
            ColumnSpec("Description", SemanticType.OTHER, 0.25, "left"),
            ColumnSpec("Debit", SemanticType.AMOUNT, 0.13, "right"),
            ColumnSpec("Credit", SemanticType.AMOUNT, 0.13, "right"),
            ColumnSpec("Balance", SemanticType.BALANCE, 0.14, "right"),
            ColumnSpec("GL Code", SemanticType.ACCOUNT, 0.15, "left"),
        ],
        supports_subtotals=True,
        typical_row_count_range=(20, 100),
        has_grid_lines=True,
        font_name="Helvetica",
        font_size=9,
        header_font_size=10,
        row_height=14.0,
    )


def validate_template(template: TableTemplate) -> bool:
    """
    Validate that column widths sum to approximately 1.0.

    Returns True if valid, raises ValueError if not.
    """
    total_width = sum(spec.width_ratio for spec in template.column_specs)
    if not (0.98 <= total_width <= 1.02):
        raise ValueError(
            f"Column widths sum to {total_width:.3f}, expected ~1.0 for "
            f"template {template.vendor_system}/{template.table_type.value}"
        )
    return True


def get_template(table_type: TableType, vendor: str = "AKAM_NEW") -> TableTemplate:
    """Get a table template by type and vendor."""
    if table_type == TableType.CASH_OUT:
        return get_cash_out_template(vendor)
    elif table_type == TableType.CASH_IN:
        return get_cash_in_template(vendor)
    elif table_type == TableType.BUDGET:
        return get_budget_template(vendor)
    elif table_type == TableType.UNPAID:
        return get_unpaid_template(vendor)
    elif table_type == TableType.AGING:
        return get_aging_template(vendor)
    elif table_type == TableType.GL:
        return get_gl_template(vendor)
    else:
        # Default to CASH_OUT for OTHER types
        return get_cash_out_template(vendor)


def select_column_synonyms(
    column_specs: List[ColumnSpec],
    rng
) -> List[str]:
    """
    Select random synonyms for column headers.

    Returns list of header names with synonyms applied.
    """
    headers = []
    for spec in column_specs:
        name = spec.name

        # Date columns
        if name in ["Date", "Invoice Date"]:
            name = rng.choice(INVOICE_DATE_SYNONYMS)
        elif name == "Check Date":
            name = rng.choice(CHECK_DATE_SYNONYMS)
        elif name == "Due Date":
            name = rng.choice(["Due Date", "Due", "Pay By", "Due By"])

        # Vendor/payee columns
        elif name in ["Vendor", "Owner", "Resident"]:
            name = rng.choice(VENDOR_SYNONYMS)
        elif name == "Paid To":
            name = rng.choice(PAYEE_SYNONYMS)
        elif name == "VEND":
            name = rng.choice(VENDOR_CODE_SYNONYMS)

        # Reference number columns
        elif name in ["Check #", "Receipt #", "CK NO"]:
            name = rng.choice(CHECK_SYNONYMS)
        elif name == "Invoice #":
            name = rng.choice(INVOICE_SYNONYMS)
        elif name == "P/O":
            name = rng.choice(PO_SYNONYMS)
        elif name == "Reference":
            name = rng.choice(["Reference", "Ref #", "Ref", "Trans #", "Txn #"])

        # Amount/balance columns
        elif name == "Amount":
            name = rng.choice(AMOUNT_SYNONYMS)
        elif name in ["Balance", "Close Bal"]:
            name = rng.choice(CLOSING_BAL_SYNONYMS)
        elif name == "Open Bal":
            name = rng.choice(OPENING_BAL_SYNONYMS)
        elif name == "Base Charge":
            name = rng.choice(BASE_CHARGE_SYNONYMS)
        elif name == "Shares":
            name = rng.choice(SHARES_SYNONYMS)
        elif name == "Paid":
            name = rng.choice(["Paid", "Payment", "Received", "Amt Paid"])

        # Account columns
        elif name in ["GL Code", "G/L"]:
            name = rng.choice(GL_CODE_SYNONYMS)
        elif name in ["Acct No", "Acct"]:
            name = rng.choice(TENANT_CODE_SYNONYMS)
        elif name in ["Unit", "Apt"]:
            name = rng.choice(UNIT_SYNONYMS)

        # Description/other columns
        elif name in ["Description", "Expense Type", "Charges"]:
            name = rng.choice(DESCRIPTION_SYNONYMS)
        elif name == "Remarks":
            name = rng.choice(REMARKS_SYNONYMS)
        elif name == "Status":
            name = rng.choice(STATUS_SYNONYMS)

        # Keep original name if no synonym mapping
        headers.append(name)
    return headers
