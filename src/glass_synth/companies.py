"""Real NYC CIRA co-op and condo management companies for synthetic data generation.

Based on research from The Real Deal, CIRA sources, and current NYC property management databases.
Current as of December 2025.
"""

from dataclasses import dataclass
from typing import List, Tuple
import random


@dataclass
class ManagementCompany:
    """NYC management company with associated buildings."""
    name: str
    short_name: str
    buildings: List[str]
    boroughs: List[str]
    property_types: List[str]  # COOP, CONDO, MIXED


# Top 10 real NYC management companies (ranked by units managed)
MANAGEMENT_COMPANIES = [
    ManagementCompany(
        name="FirstService Residential",
        short_name="FSR",
        buildings=[
            "432 Park Avenue",
            "8 Spruce Street",
            "80 DeKalb Avenue",
            "One Manhattan Square",
            "The Greenwich Lane",
            "15 Central Park West",
        ],
        boroughs=["Manhattan", "Brooklyn"],
        property_types=["CONDO", "COOP"],
    ),
    ManagementCompany(
        name="Douglas Elliman Property Management",
        short_name="DEPM",
        buildings=[
            "Park Terrace Gardens Inc",
            "The Beresford",
            "The Eldorado",
            "Central Park South Towers",
            "Fifth Avenue Place",
            "Sutton Place Towers",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP", "CONDO"],
    ),
    ManagementCompany(
        name="AKAM Associates",
        short_name="AKAM",
        buildings=[
            "245 East 72nd Owners Corporation",
            "Park Avenue Tower",
            "Madison Square Owners",
            "Gramercy Owners Corp",
            "Murray Hill Towers",
            "Brooklyn Heights Cooperative",
        ],
        boroughs=["Manhattan", "Brooklyn"],
        property_types=["COOP", "CONDO"],
    ),
    ManagementCompany(
        name="Halstead Management",
        short_name="Halstead",
        buildings=[
            "Gramercy Park Towers",
            "Tudor City Place",
            "Kips Bay Towers",
            "Murray Hill Manor",
            "Lexington Towers",
            "East Side Cooperative",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP", "CONDO"],
    ),
    ManagementCompany(
        name="Rose Associates",
        short_name="Rose",
        buildings=[
            "Metro Tower",
            "Riverdale Towers",
            "Tribeca Green",
            "The Lucida",
            "70 Pine Street",
            "One Brooklyn Bridge Park",
        ],
        boroughs=["Manhattan", "Brooklyn", "Bronx"],
        property_types=["CONDO", "RENTAL"],
    ),
    ManagementCompany(
        name="Orsid Realty",
        short_name="ORSID",
        buildings=[
            "Lindenwood Owners Corp",
            "245 East 72nd Street",
            "Carnegie Hill Towers",
            "Upper East Side Co-op",
            "Yorkville Towers",
            "Lenox Hill Cooperative",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP"],
    ),
    ManagementCompany(
        name="Midboro Management",
        short_name="Midboro",
        buildings=[
            "Lincoln Towers",
            "West End Towers",
            "Riverside Owners Corp",
            "Columbus Circle Condos",
            "Central Park Cooperative",
            "Upper West Towers",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP", "CONDO"],
    ),
    ManagementCompany(
        name="Wavecrest Management",
        short_name="Wavecrest",
        buildings=[
            "Queens Village Co-op",
            "Rochdale Village",
            "Co-op City Tower A",
            "Parkchester Towers",
            "Bay Terrace Cooperative",
            "Fresh Meadows Gardens",
        ],
        boroughs=["Queens", "Bronx", "Brooklyn"],
        property_types=["COOP"],
    ),
    ManagementCompany(
        name="Charles H. Greenthal Management",
        short_name="Greenthal",
        buildings=[
            "Upper West Towers",
            "Riverside Drive Owners",
            "Amsterdam Cooperative",
            "West 86th Owners Corp",
            "Morningside Heights Co-op",
            "Columbia Terrace",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP"],
    ),
    ManagementCompany(
        name="Argo Real Estate",
        short_name="Argo",
        buildings=[
            "Park Avenue Place",
            "Madison Square Gardens",
            "Fifth Avenue Cooperative",
            "Central Park Towers",
            "Lexington Avenue Condos",
            "East End Towers",
        ],
        boroughs=["Manhattan"],
        property_types=["COOP", "CONDO"],
    ),
]


# Property manager names for TEMPLATE headers (synthetic/generated)
# Used to populate "Prepared by: {manager}" or "Manager: {name}" in headers
PROPERTY_MANAGERS = [
    # Common names
    "John Smith", "Maria Garcia", "David Chen", "Sarah Johnson",
    "Michael Brown", "Jennifer Lee", "Robert Williams", "Lisa Anderson",
    "James Martinez", "Michelle Thompson", "William Davis", "Angela Wilson",
    "Christopher Taylor", "Patricia Moore", "Daniel Jackson", "Nancy White",
    "Matthew Harris", "Karen Martin", "Joseph Clark", "Betty Lewis",
    # More diverse names
    "Ahmed Hassan", "Priya Patel", "Tomasz Kowalski", "Yuki Tanaka",
    "Olga Petrov", "Marcus Johnson", "Elena Rodriguez", "Kwame Asante",
]


def get_random_manager(rng=None) -> str:
    """Get a random property manager name."""
    if rng is None:
        rng = random.Random()
    return rng.choice(PROPERTY_MANAGERS)


# Report/schedule types commonly seen in CIRA financial packages
REPORT_TYPES = [
    # Cash schedules
    ("Schedule B - Statement of Paid Bills", "CASH_OUT"),
    ("Cash Disbursements", "CASH_OUT"),
    ("Check Register", "CASH_OUT"),
    ("Schedule D - Collection Status", "CASH_IN"),
    ("Cash Receipts", "CASH_IN"),
    ("Collection Status Report", "CASH_IN"),

    # Financial statements
    ("Income Statement", "BUDGET"),
    ("Budget vs Actual", "BUDGET"),
    ("Statement of Revenue and Expenses", "BUDGET"),
    ("Operating Statement", "BUDGET"),

    # Balance sheet & position
    ("Balance Sheet", "BALANCE_SHEET"),
    ("Statement of Financial Position", "BALANCE_SHEET"),

    # Receivables/aging
    ("Aged Receivables", "AGING"),
    ("Arrears Report", "AGING"),
    ("Collection Status by Age", "AGING"),
    ("Owner Aging Report", "AGING"),

    # Payables
    ("Unpaid Bills", "UNPAID"),
    ("Open Payables", "UNPAID"),
    ("Accounts Payable Aging", "UNPAID"),

    # General ledger
    ("General Ledger", "GL"),
    ("GL Detail", "GL"),
    ("Account Activity", "GL"),
    ("Transaction Detail", "GL"),
]


def get_random_company(rng: random.Random = None) -> ManagementCompany:
    """Get a random management company."""
    if rng is None:
        rng = random.Random()
    return rng.choice(MANAGEMENT_COMPANIES)


def get_random_building(company: ManagementCompany, rng: random.Random = None) -> str:
    """Get a random building for a management company."""
    if rng is None:
        rng = random.Random()
    return rng.choice(company.buildings)


def get_company_by_name(name: str) -> ManagementCompany:
    """Get a company by name (partial match)."""
    name_lower = name.lower()
    for company in MANAGEMENT_COMPANIES:
        if name_lower in company.name.lower() or name_lower in company.short_name.lower():
            return company
    return MANAGEMENT_COMPANIES[0]  # Default to FirstService


def get_train_val_split(
    val_ratio: float = 0.2,
    seed: int = 42
) -> Tuple[List[ManagementCompany], List[ManagementCompany]]:
    """
    Split companies into train/validation sets.

    Uses company-level split to avoid data leakage:
    - Training: 8 companies
    - Validation: 2 companies

    Returns:
        Tuple of (train_companies, val_companies)
    """
    rng = random.Random(seed)
    shuffled = MANAGEMENT_COMPANIES.copy()
    rng.shuffle(shuffled)

    num_val = max(1, int(len(shuffled) * val_ratio))
    val_companies = shuffled[:num_val]
    train_companies = shuffled[num_val:]

    return train_companies, val_companies


def generate_page_header_text(
    report_type: str,
    building_name: str,
    address: str = None,
    period: str = None
) -> str:
    """
    Generate a PAGE_HEADER (section title) text.

    PAGE_HEADER is the report/schedule name, distinct from HEADER (column names).

    Args:
        report_type: Type of report (from REPORT_TYPES)
        building_name: Building/owner corporation name
        address: Optional address
        period: Optional period (e.g., "April 2025")

    Returns:
        Section title text like "Collection Status 245 East 72nd Owners Corporation"
    """
    parts = [report_type]

    if building_name:
        parts.append(building_name)

    if address:
        parts.append(address)

    if period:
        parts.append(f"For Period Ending {period}")

    return " - ".join(parts) if len(parts) > 1 else parts[0]


def generate_template_text(
    company: ManagementCompany,
    building_name: str,
    template_type: str = "company_name"
) -> str:
    """
    Generate TEMPLATE (design layer) text that appears on every page.

    Template elements are visual design elements, NOT content:
    - Company name at top
    - Report package title
    - Page numbers

    Args:
        company: Management company
        building_name: Building name
        template_type: One of "company_name", "report_title", "page_number"

    Returns:
        Template text
    """
    if template_type == "company_name":
        return f"{building_name.upper()}"
    elif template_type == "report_title":
        return f"Monthly Financial Package - {building_name}"
    elif template_type == "prepared_for":
        return f"{building_name.upper()} --- PREPARED FOR ---"
    elif template_type == "footer":
        return f"Prepared by {company.name}"
    else:
        return building_name


# Vocabulary sets for distinguishing PAGE_HEADER from HEADER
PAGE_HEADER_VOCAB = {
    # Report/schedule names
    'collection', 'status', 'income', 'statement', 'balance', 'sheet',
    'budget', 'comparison', 'cash', 'disbursements', 'receivables',
    'aging', 'summary', 'report', 'schedule', 'analysis', 'ledger',
    'journal', 'trial', 'owners', 'corporation', 'management',
    'monthly', 'financial', 'package', 'period', 'ending',
    'prepared', 'for', 'quarterly', 'annual', 'ytd', 'year-to-date',
}

COLUMN_HEADER_VOCAB = {
    # Column/field names
    'date', 'amount', 'balance', 'total', 'vendor', 'account', 'check',
    'payment', 'debit', 'credit', 'unit', 'tenant', 'charge', 'due',
    'paid', 'invoice', 'ref', 'memo', 'gl', 'code', 'description',
    'opening', 'closing', 'current', 'shares', 'status', 'name',
    'legal', 'received', 'charges', 'credits', 'prior', 'ytd',
    'budget', 'actual', 'variance', 'acct', 'no', 'number',
}


def has_page_header_vocab(text: str) -> bool:
    """Check if text has PAGE_HEADER vocabulary."""
    words = set(text.lower().split())
    return len(words & PAGE_HEADER_VOCAB) >= 2


def has_column_header_vocab(text: str) -> bool:
    """Check if text has COLUMN_HEADER vocabulary."""
    words = set(text.lower().split())
    return len(words & COLUMN_HEADER_VOCAB) >= 2
