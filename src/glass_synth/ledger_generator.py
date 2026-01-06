"""Generate balanced journal entries / ledger transactions."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
import numpy as np
from faker import Faker

from .chart_of_accounts import (
    GLAccount, GLCategory, FundCode,
    get_expense_accounts, get_revenue_accounts
)


@dataclass
class JournalEntryLine:
    """A single line in a journal entry."""
    txn_id: str
    date: date
    post_date: date
    gl_code: str
    gl_name: str
    fund: str
    amount: float  # Always positive
    dc: str  # "D" for debit, "C" for credit
    description: str
    vendor: Optional[str]
    check_number: Optional[str] = None


@dataclass
class CashTransaction:
    """A cash disbursement or receipt transaction."""
    txn_id: str
    date: date  # Transaction date (invoice date for disbursements)
    vendor: str
    gl_code: str
    gl_name: str
    description: str
    amount: float
    check_number: str
    is_disbursement: bool  # True for cash out, False for cash in

    # Enhanced fields for CASH_OUT
    invoice_number: Optional[str] = None  # INV-12345
    invoice_date: Optional[date] = None   # When invoice was received
    check_date: Optional[date] = None     # When payment was made
    vendor_code: Optional[str] = None     # 4-char vendor identifier
    po_number: Optional[str] = None       # Purchase order number
    remarks: Optional[str] = None         # Notes/remarks

    # Enhanced fields for CASH_IN
    account_code: Optional[str] = None    # Tenant/unit account code
    unit_id: Optional[str] = None         # Apartment/unit number
    opening_balance: Optional[float] = None  # Balance before transaction
    base_charge: Optional[float] = None   # Monthly assessment amount
    shares: Optional[int] = None          # Co-op shares (for COOP properties)
    status: Optional[str] = None          # Current, Delinquent, Prepaid


# Constants for data generation
PAYMENT_STATUSES = ["Current", "Paid", "Open", "Pending", "Delinquent", "Prepaid"]
VENDOR_CODE_PREFIXES = ["V", "O", "P", "S", "C", "M", "A", "B"]

NOTE_CONTENT_TEMPLATES = [
    "* {category} includes prior period adjustments",
    "See attached schedule for detail",
    "** Amount reflects {percent}% discount applied",
    "Note: Prepaid amounts shown as credits",
    "Amounts subject to final reconciliation",
    "* Includes {month} late fees",
    "Per board resolution",
    "--- Continued ---",
    "* See footnote {num}",
    "Reclassified per audit",
    "Adjusted for accrual",
    "* Estimated amount",
    "",  # Empty separator row
]


def generate_invoice_number(rng: np.random.Generator) -> str:
    """Generate realistic invoice number."""
    formats = [
        lambda: f"INV-{rng.integers(10000, 99999)}",
        lambda: f"{rng.integers(100000, 999999)}",
        lambda: f"{chr(ord('A') + rng.integers(0, 26))}{rng.integers(1000, 9999)}",
        lambda: f"INV{rng.integers(2024, 2026)}-{rng.integers(100, 999)}",
        lambda: f"{rng.integers(1, 12):02d}-{rng.integers(10000, 99999)}",
    ]
    return rng.choice(formats)()


def generate_vendor_code(vendor_name: str, rng: np.random.Generator) -> str:
    """Generate 4-character vendor code from vendor name."""
    # Use first letter + random chars based on name hash
    prefix = rng.choice(VENDOR_CODE_PREFIXES)
    code_num = hash(vendor_name) % 999
    return f"{prefix}{code_num:03d}"


def generate_po_number(rng: np.random.Generator) -> Optional[str]:
    """Generate purchase order number (30% chance of having one)."""
    if rng.random() < 0.30:
        return f"PO-{rng.integers(1000, 9999)}"
    return None


def generate_account_code(unit_id: str, rng: np.random.Generator) -> str:
    """Generate account/tenant code."""
    formats = [
        lambda: f"A{unit_id.replace('-', '')}{rng.integers(0, 9)}",
        lambda: f"{rng.integers(100, 999)}-{unit_id}",
        lambda: f"T{rng.integers(10000, 99999)}",
    ]
    return rng.choice(formats)()


def generate_unit_id(rng: np.random.Generator) -> str:
    """Generate apartment/unit identifier."""
    formats = [
        lambda: f"{rng.integers(1, 30)}{chr(ord('A') + rng.integers(0, 6))}",
        lambda: f"{rng.integers(100, 999)}",
        lambda: f"{rng.integers(1, 5)}F-{rng.integers(1, 10):02d}",
        lambda: f"PH{rng.integers(1, 5)}",
    ]
    return rng.choice(formats)()


def generate_shares(property_type: str, rng: np.random.Generator) -> Optional[int]:
    """Generate co-op shares (only for COOP properties)."""
    if property_type == "COOP":
        return int(rng.integers(50, 500))
    return None


def generate_base_charge(rng: np.random.Generator) -> float:
    """Generate monthly base assessment charge."""
    # Realistic monthly maintenance amounts
    return round(rng.uniform(500, 3500), 2)


def generate_opening_balance(rng: np.random.Generator) -> float:
    """Generate opening balance (can be negative for prepaid)."""
    # 80% have zero or small positive balance, 15% delinquent, 5% prepaid
    r = rng.random()
    if r < 0.80:
        return round(rng.uniform(0, 500), 2)
    elif r < 0.95:
        return round(rng.uniform(500, 5000), 2)  # Delinquent
    else:
        return round(rng.uniform(-1000, 0), 2)  # Prepaid (negative)


def generate_status(opening_balance: float, rng: np.random.Generator) -> str:
    """Generate payment status based on balance."""
    if opening_balance < 0:
        return "Prepaid"
    elif opening_balance > 1000:
        return rng.choice(["Delinquent", "Past Due", "Legal"])
    elif opening_balance > 0:
        return rng.choice(["Open", "Pending", "Current"])
    else:
        return rng.choice(["Current", "Paid", "Active"])


def generate_note_content(gl_name: str, rng: np.random.Generator) -> str:
    """Generate realistic note/footnote content."""
    template = rng.choice(NOTE_CONTENT_TEMPLATES)
    if not template:
        return ""
    return template.format(
        category=gl_name.split()[0] if gl_name else "Account",
        percent=int(rng.integers(2, 15)),
        month=rng.choice(["January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]),
        num=int(rng.integers(1, 5)),
    )


def generate_monthly_ledger(
    accounts: List[GLAccount],
    start_date: date,
    end_date: date,
    rng: np.random.Generator,
    num_transactions: int = 50,
    property_type: str = "CONDO"
) -> Tuple[List[JournalEntryLine], List[CashTransaction]]:
    """
    Generate balanced journal entries for a month.

    Args:
        accounts: List of GL accounts to use
        start_date: Start of date range
        end_date: End of date range
        rng: Random number generator
        num_transactions: Number of transactions to generate
        property_type: CONDO, HOA, COOP, or MIXED_USE (affects shares generation)

    Returns:
        Tuple of (journal_entries, cash_transactions)
    """
    fake = Faker()
    Faker.seed(int(rng.integers(0, 2**31)))

    journal_entries: List[JournalEntryLine] = []
    cash_transactions: List[CashTransaction] = []

    expense_accounts = get_expense_accounts(accounts)
    revenue_accounts = get_revenue_accounts(accounts)

    # Generate expense transactions (disbursements)
    num_expenses = int(num_transactions * 0.7)  # 70% expenses
    for i in range(num_expenses):
        txn_id = f"JE-{i+1:06d}"
        invoice_date = _random_date(start_date, end_date, rng)
        # Check date is typically 5-30 days after invoice date
        check_date = invoice_date + timedelta(days=int(rng.integers(5, 30)))
        post_date = check_date + timedelta(days=int(rng.integers(0, 3)))

        # Pick a random expense account
        expense_acct = rng.choice(expense_accounts)

        # Generate realistic amount based on expense type
        amount = _generate_expense_amount(expense_acct.subcategory, rng)

        vendor_name = fake.company()
        check_num = f"{rng.integers(1000, 9999)}"
        description = _generate_expense_description(expense_acct.name, vendor_name)

        # Generate enhanced fields for CASH_OUT
        invoice_num = generate_invoice_number(rng)
        vendor_code = generate_vendor_code(vendor_name, rng)
        po_num = generate_po_number(rng)
        remarks = rng.choice([
            None, None, None,  # 60% no remarks
            "Approved by board",
            "Monthly recurring",
            "See attached invoice",
            f"PO approved {invoice_date.strftime('%m/%d')}",
        ])

        # Debit the expense account
        journal_entries.append(JournalEntryLine(
            txn_id=txn_id,
            date=invoice_date,
            post_date=post_date,
            gl_code=expense_acct.code,
            gl_name=expense_acct.name,
            fund=expense_acct.fund.value,
            amount=amount,
            dc="D",
            description=description,
            vendor=vendor_name,
            check_number=check_num,
        ))

        # Record as cash transaction for CASH_OUT table with enhanced fields
        cash_transactions.append(CashTransaction(
            txn_id=txn_id,
            date=invoice_date,
            vendor=vendor_name,
            gl_code=expense_acct.code,
            gl_name=expense_acct.name,
            description=description,
            amount=amount,
            check_number=check_num,
            is_disbursement=True,
            # Enhanced CASH_OUT fields
            invoice_number=invoice_num,
            invoice_date=invoice_date,
            check_date=check_date,
            vendor_code=vendor_code,
            po_number=po_num,
            remarks=remarks,
        ))

    # Generate revenue transactions (receipts)
    num_revenues = num_transactions - num_expenses
    for i in range(num_revenues):
        txn_id = f"JE-{num_expenses + i + 1:06d}"
        txn_date = _random_date(start_date, end_date, rng)
        post_date = txn_date + timedelta(days=int(rng.integers(0, 3)))

        # Pick a random revenue account
        revenue_acct = rng.choice(revenue_accounts)

        # Generate realistic amount
        amount = _generate_revenue_amount(revenue_acct.subcategory, rng)

        # Generate enhanced CASH_IN fields
        unit_id = generate_unit_id(rng)
        account_code = generate_account_code(unit_id, rng)
        owner_name = fake.name()
        receipt_num = f"R{rng.integers(10000, 99999)}"
        description = _generate_revenue_description(revenue_acct.name)

        # Generate balance-related fields
        opening_balance = generate_opening_balance(rng)
        base_charge = generate_base_charge(rng)
        shares = generate_shares(property_type, rng)
        status = generate_status(opening_balance, rng)

        # Credit the revenue account
        journal_entries.append(JournalEntryLine(
            txn_id=txn_id,
            date=txn_date,
            post_date=post_date,
            gl_code=revenue_acct.code,
            gl_name=revenue_acct.name,
            fund=revenue_acct.fund.value,
            amount=amount,
            dc="C",
            description=description,
            vendor=f"Unit {unit_id} - {owner_name}",
            check_number=receipt_num,
        ))

        # Record as cash transaction for CASH_IN table with enhanced fields
        cash_transactions.append(CashTransaction(
            txn_id=txn_id,
            date=txn_date,
            vendor=owner_name,  # Just owner name, unit is separate
            gl_code=revenue_acct.code,
            gl_name=revenue_acct.name,
            description=description,
            amount=amount,
            check_number=receipt_num,
            is_disbursement=False,
            # Enhanced CASH_IN fields
            account_code=account_code,
            unit_id=unit_id,
            opening_balance=opening_balance,
            base_charge=base_charge,
            shares=shares,
            status=status,
        ))

    # Sort by date
    journal_entries.sort(key=lambda x: x.date)
    cash_transactions.sort(key=lambda x: x.date)

    return journal_entries, cash_transactions


def _random_date(start: date, end: date, rng: np.random.Generator) -> date:
    """Generate a random date between start and end."""
    delta = (end - start).days
    random_days = rng.integers(0, max(1, delta + 1))
    return start + timedelta(days=int(random_days))


def _generate_expense_amount(subcategory: str, rng: np.random.Generator) -> float:
    """Generate realistic expense amounts based on subcategory."""
    ranges = {
        "ADMIN": (500, 5000),
        "LEGAL": (1000, 15000),
        "INSURANCE": (2000, 20000),
        "UTILITIES": (200, 3000),
        "MAINTENANCE": (100, 5000),
        "CONTRACTS": (500, 8000),
        "RESERVE_TRANSFER": (1000, 10000),
    }
    min_amt, max_amt = ranges.get(subcategory, (100, 5000))
    # Use log-normal distribution for more realistic amounts
    mean = np.log((min_amt + max_amt) / 2)
    std = 0.5
    amount = rng.lognormal(mean, std)
    amount = max(min_amt, min(max_amt, amount))
    return round(amount, 2)


def _generate_revenue_amount(subcategory: str, rng: np.random.Generator) -> float:
    """Generate realistic revenue amounts based on subcategory."""
    ranges = {
        "ASSESSMENTS": (500, 5000),  # Monthly assessment
        "FEES": (25, 500),  # Late fees
        "INTEREST": (10, 200),
        "ANCILLARY": (50, 500),
        "OTHER": (25, 1000),
    }
    min_amt, max_amt = ranges.get(subcategory, (100, 2000))
    mean = np.log((min_amt + max_amt) / 2)
    std = 0.4
    amount = rng.lognormal(mean, std)
    amount = max(min_amt, min(max_amt, amount))
    return round(amount, 2)


def _generate_expense_description(account_name: str, vendor: str) -> str:
    """Generate description for expense transaction."""
    prefixes = [
        f"Payment to {vendor}",
        f"{account_name}",
        f"Invoice payment - {vendor}",
        f"{vendor} services",
    ]
    return prefixes[hash(vendor) % len(prefixes)]


def _generate_revenue_description(account_name: str) -> str:
    """Generate description for revenue transaction."""
    if "Assessment" in account_name:
        return "Monthly assessment"
    elif "Late" in account_name:
        return "Late fee charge"
    elif "Interest" in account_name:
        return "Interest earned"
    elif "Parking" in account_name:
        return "Parking fee"
    else:
        return "Miscellaneous income"
