"""Chart of Accounts (CoA) generation for CIRA financial statements."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import numpy as np
import re


class GLCategory(Enum):
    """General Ledger account categories per CIRA standards."""
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"
    RESERVE = "RESERVE"


class FundCode(Enum):
    """Standard CIRA fund codes."""
    OPERATING = "01"
    RESERVE = "02"
    SPECIAL_ASSESSMENT = "03"
    PAYROLL = "04"


@dataclass
class GLAccount:
    """Represents a General Ledger account."""
    code: str  # e.g., "01-6015-00" or "6015"
    name: str  # e.g., "Legal Fees - Collection"
    category: GLCategory
    subcategory: str  # e.g., "LEGAL", "UTILITIES"
    fund: FundCode
    base_code: int  # numeric base code (e.g., 6015)


# GL code ranges per CIRA standards:
# Revenue: 4000-4999
# Expenses: 6000-9000
# Reserves: 3000-3199

# Minimal set of accounts for Phase 1
REVENUE_ACCOUNTS = [
    (4010, "Assessment Income", "ASSESSMENTS"),
    (4020, "Late Charges", "FEES"),
    (4100, "Interest Income", "INTEREST"),
    (4110, "Parking Income", "ANCILLARY"),
    (4190, "Other Income", "OTHER"),
]

EXPENSE_ACCOUNTS = [
    (6010, "Management Fees", "ADMIN"),
    (6015, "Legal Fees", "LEGAL"),
    (6020, "Accounting Fees", "ADMIN"),
    (6100, "Insurance", "INSURANCE"),
    (6200, "Electricity", "UTILITIES"),
    (6210, "Gas", "UTILITIES"),
    (6220, "Water & Sewer", "UTILITIES"),
    (6300, "General Maintenance", "MAINTENANCE"),
    (6310, "Landscaping", "MAINTENANCE"),
    (6400, "Janitorial Services", "CONTRACTS"),
    (6500, "Reserve Allocation", "RESERVE_TRANSFER"),
]

RESERVE_ACCOUNTS = [
    (3010, "Roof Reserve", "BUILDING"),
    (3020, "Elevator Reserve", "BUILDING"),
    (3030, "Painting Reserve", "BUILDING"),
]


def format_gl_code(base_code: int, mask: str, fund: FundCode) -> str:
    """
    Format a GL code according to the specified mask.

    Masks:
    - "NNNN": 4-digit code (e.g., "6015")
    - "NNNNN": 5-digit code (e.g., "06015")
    - "NN-NNNN-NN": fund-code-suffix format (e.g., "01-6015-00")
    - "NNNNNN": 6-digit combined (e.g., "016015")
    """
    if mask == "NNNN":
        return f"{base_code:04d}"
    elif mask == "NNNNN":
        return f"{base_code:05d}"
    elif mask == "NN-NNNN-NN":
        return f"{fund.value}-{base_code:04d}-00"
    elif mask == "NNNNNN":
        return f"{fund.value}{base_code:04d}"
    else:
        raise ValueError(f"Unknown GL mask: {mask}")


def get_mask_regex(mask: str) -> str:
    """Return regex pattern for validating GL codes against a mask."""
    if mask == "NNNN":
        return r"^\d{4}$"
    elif mask == "NNNNN":
        return r"^\d{5}$"
    elif mask == "NN-NNNN-NN":
        return r"^\d{2}-\d{4}-\d{2}$"
    elif mask == "NNNNNN":
        return r"^\d{6}$"
    else:
        raise ValueError(f"Unknown GL mask: {mask}")


def validate_gl_code(code: str, mask: str) -> bool:
    """Validate that a GL code matches the expected mask."""
    pattern = get_mask_regex(mask)
    return bool(re.match(pattern, code))


def build_chart_of_accounts(
    gl_mask: str,
    fund: FundCode = FundCode.OPERATING,
    rng: Optional[np.random.Generator] = None
) -> List[GLAccount]:
    """
    Build a chart of accounts for a given GL mask format.

    For Phase 1, returns a fixed set of ~15 accounts.
    """
    accounts = []

    # Add revenue accounts
    for base_code, name, subcategory in REVENUE_ACCOUNTS:
        code = format_gl_code(base_code, gl_mask, fund)
        accounts.append(GLAccount(
            code=code,
            name=name,
            category=GLCategory.REVENUE,
            subcategory=subcategory,
            fund=fund,
            base_code=base_code,
        ))

    # Add expense accounts
    for base_code, name, subcategory in EXPENSE_ACCOUNTS:
        code = format_gl_code(base_code, gl_mask, fund)
        accounts.append(GLAccount(
            code=code,
            name=name,
            category=GLCategory.EXPENSE,
            subcategory=subcategory,
            fund=fund,
            base_code=base_code,
        ))

    # Add reserve accounts (use RESERVE fund)
    reserve_fund = FundCode.RESERVE
    for base_code, name, subcategory in RESERVE_ACCOUNTS:
        code = format_gl_code(base_code, gl_mask, reserve_fund)
        accounts.append(GLAccount(
            code=code,
            name=name,
            category=GLCategory.RESERVE,
            subcategory=subcategory,
            fund=reserve_fund,
            base_code=base_code,
        ))

    return accounts


def get_accounts_by_category(
    accounts: List[GLAccount],
    category: GLCategory
) -> List[GLAccount]:
    """Filter accounts by category."""
    return [a for a in accounts if a.category == category]


def get_expense_accounts(accounts: List[GLAccount]) -> List[GLAccount]:
    """Get all expense accounts."""
    return get_accounts_by_category(accounts, GLCategory.EXPENSE)


def get_revenue_accounts(accounts: List[GLAccount]) -> List[GLAccount]:
    """Get all revenue accounts."""
    return get_accounts_by_category(accounts, GLCategory.REVENUE)
