"""Command-line interface for the synthetic data generator."""

import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple, Any
import numpy as np
from faker import Faker

from .config import GeneratorConfig, load_config
from .chart_of_accounts import build_chart_of_accounts, FundCode, GLAccount
from .ledger_generator import generate_monthly_ledger, CashTransaction
from .table_templates import TableTemplate, TableType, LayoutType, get_template
from .pdf_renderer import PDFRenderer, RenderedTable
from .labels_writer import write_labels, write_document_metadata, clear_labels


def sample_from_distribution(distribution: dict, rng: np.random.Generator) -> str:
    """Sample a key from a distribution dict."""
    keys = list(distribution.keys())
    probs = list(distribution.values())
    return rng.choice(keys, p=probs)


def sample_table_type(config: GeneratorConfig, rng: np.random.Generator) -> TableType:
    """Sample a table type from the configured distribution."""
    # Normalize table_mix to actual probabilities
    table_types = []
    probs = []
    for table_type, (min_prop, max_prop) in config.table_mix.items():
        table_types.append(table_type)
        # Use midpoint of range
        probs.append((min_prop + max_prop) / 2)

    # Normalize probabilities
    total = sum(probs)
    probs = [p / total for p in probs]

    selected = rng.choice(table_types, p=probs)
    return TableType(selected)


def generate_budget_data(
    accounts: List[GLAccount],
    period_start: date,
    rng: np.random.Generator,
    num_rows: int = 25
) -> List[dict]:
    """Generate data rows for a budget/income statement table."""
    rows = []

    # Group accounts into categories based on base_code ranges
    revenue_accounts = [a for a in accounts if 4000 <= a.base_code < 5000]
    expense_accounts = [a for a in accounts if 6000 <= a.base_code < 9000]

    # Use a subset of accounts
    selected = (revenue_accounts[:5] + expense_accounts[:min(num_rows-5, len(expense_accounts))])

    for account in selected:
        current = float(rng.uniform(500, 15000))
        ytd_actual = current * float(rng.uniform(2.5, 4.0))
        ytd_budget = ytd_actual * float(rng.uniform(0.85, 1.15))
        annual_budget = ytd_budget * 12 / int(period_start.month)
        variance = ytd_budget - ytd_actual

        rows.append({
            "account": f"{account.code} {account.name}",
            "current": current,
            "ytd_actual": ytd_actual,
            "ytd_budget": ytd_budget,
            "annual_budget": annual_budget,
            "variance": variance,
        })

    return rows


def generate_unpaid_data(
    accounts: List[GLAccount],
    period_end: date,
    rng: np.random.Generator,
    fake: Faker,
    num_rows: int = 15
) -> List[dict]:
    """Generate data rows for unpaid bills / open payables table."""
    rows = []
    expense_accounts = [a for a in accounts if 6000 <= a.base_code < 9000]

    for i in range(num_rows):
        invoice_date = period_end - timedelta(days=int(rng.integers(5, 60)))
        due_date = invoice_date + timedelta(days=int(rng.choice([15, 30, 45, 60])))
        account = rng.choice(expense_accounts) if expense_accounts else accounts[0]

        rows.append({
            "date": invoice_date,
            "vendor": fake.company(),
            "invoice_num": f"INV-{rng.integers(10000, 99999)}",
            "due_date": due_date,
            "gl_code": account.code,
            "description": f"Invoice from {fake.company()}",
            "amount": float(rng.uniform(500, 25000)),
        })

    return rows


def generate_aging_data(
    rng: np.random.Generator,
    fake: Faker,
    num_rows: int = 20
) -> List[dict]:
    """Generate data rows for aging/receivables table."""
    rows = []

    for i in range(num_rows):
        unit = f"{rng.integers(1, 30)}{rng.choice(['A', 'B', 'C', 'D'])}"
        total = float(rng.uniform(0, 15000))

        # Distribute across aging buckets
        if total > 0:
            current = total * float(rng.uniform(0, 0.5))
            remaining = total - current
            days_30 = remaining * float(rng.uniform(0, 0.4))
            remaining -= days_30
            days_60 = remaining * float(rng.uniform(0, 0.5))
            remaining -= days_60
            days_90 = remaining * float(rng.uniform(0, 0.6))
            days_90_plus = remaining - days_90
        else:
            current = days_30 = days_60 = days_90 = days_90_plus = 0.0

        rows.append({
            "unit": unit,
            "owner": fake.name(),
            "current": current,
            "days_30": days_30,
            "days_60": days_60,
            "days_90": days_90,
            "days_90_plus": days_90_plus,
            "total": total,
        })

    return rows


def generate_gl_data(
    accounts: List[GLAccount],
    period_start: date,
    period_end: date,
    rng: np.random.Generator,
    fake: Faker,
    num_rows: int = 30
) -> List[dict]:
    """Generate data rows for general ledger table."""
    rows = []
    balance = float(rng.uniform(10000, 50000))

    # Pick a random GL account for this ledger detail
    account = rng.choice(accounts)

    current_date = period_start
    for i in range(num_rows):
        current_date = current_date + timedelta(days=int(rng.integers(0, 3)))
        if current_date > period_end:
            current_date = period_end

        is_debit = rng.random() > 0.5
        amount = float(rng.uniform(100, 5000))

        if is_debit:
            debit = amount
            credit = 0.0
            balance += amount
        else:
            debit = 0.0
            credit = amount
            balance -= amount

        rows.append({
            "date": current_date,
            "reference": f"{'CHK' if is_debit else 'DEP'}{rng.integers(1000, 9999)}",
            "description": fake.sentence(nb_words=4),
            "debit": debit,
            "credit": credit,
            "balance": balance,
            "gl_code": account.code,
        })

    return rows


def generate_document(
    doc_idx: int,
    config: GeneratorConfig,
    rng: np.random.Generator
) -> Tuple[str, List[RenderedTable], int]:
    """
    Generate a single document with tables and labels.

    Returns:
        Tuple of (doc_id, rendered_tables, page_count)
    """
    # Sample document parameters
    vendor = sample_from_distribution(config.vendor_distribution, rng)
    property_type = sample_from_distribution(config.property_type_distribution, rng)
    gl_mask = sample_from_distribution(config.gl_mask_distribution, rng)
    degradation_level = int(sample_from_distribution(
        {str(k): v for k, v in config.degradation_distribution.items()}, rng
    ))

    # Sample layout type and orientation
    layout_type_str = sample_from_distribution(config.layout_distribution, rng)
    layout_type = LayoutType(layout_type_str)
    orientation = sample_from_distribution(config.orientation_distribution, rng)

    # Create document ID
    period_str = config.period_start.strftime("%Y-%m")
    doc_id = f"{vendor}__{doc_idx:05d}__{period_str}"

    # Build chart of accounts
    accounts = build_chart_of_accounts(gl_mask, FundCode.OPERATING, rng)

    # Generate ledger entries
    journal_entries, cash_transactions = generate_monthly_ledger(
        accounts=accounts,
        start_date=config.period_start,
        end_date=config.period_end,
        rng=rng,
        num_transactions=rng.integers(30, 80),  # Vary transaction count
        property_type=property_type,  # For generating shares in COOP properties
    )

    # Create Faker instance for generating additional data
    fake = Faker()
    fake.seed_instance(int(rng.integers(0, 2**31)))

    # Split transactions into disbursements and receipts
    disbursements = [t for t in cash_transactions if t.is_disbursement]
    receipts = [t for t in cash_transactions if not t.is_disbursement]

    # Prepare tables - tuple of (template, title, data, layout_type)
    # data can be List[CashTransaction] or List[dict] for non-cash tables
    tables_data: List[Tuple[TableTemplate, str, Any, LayoutType]] = []

    # Sample table types to include in this document
    # Each document has 1-3 tables
    num_tables = int(rng.integers(1, 4))

    for _ in range(num_tables):
        table_type = sample_table_type(config, rng)

        # Determine layout based on table type
        # Cash tables use the sampled layout; non-cash tables prefer HORIZONTAL or MATRIX
        if table_type in [TableType.CASH_OUT, TableType.CASH_IN]:
            table_layout = layout_type
        elif table_type == TableType.BUDGET:
            # Budget tables work well with MATRIX layout
            table_layout = rng.choice([LayoutType.HORIZONTAL_LEDGER, LayoutType.MATRIX],
                                       p=[0.4, 0.6])
        else:
            # Other non-cash tables use horizontal layout
            table_layout = LayoutType.HORIZONTAL_LEDGER

        template = get_template(table_type, vendor)
        title = rng.choice(template.title_options)

        if table_type == TableType.CASH_OUT:
            if disbursements:
                tables_data.append((template, title, disbursements, table_layout))
        elif table_type == TableType.CASH_IN:
            if receipts:
                tables_data.append((template, title, receipts, table_layout))
        elif table_type == TableType.BUDGET:
            budget_data = generate_budget_data(accounts, config.period_start, rng)
            tables_data.append((template, title, budget_data, table_layout))
        elif table_type == TableType.UNPAID:
            unpaid_data = generate_unpaid_data(accounts, config.period_end, rng, fake)
            tables_data.append((template, title, unpaid_data, table_layout))
        elif table_type == TableType.AGING:
            aging_data = generate_aging_data(rng, fake)
            tables_data.append((template, title, aging_data, table_layout))
        elif table_type == TableType.GL:
            gl_data = generate_gl_data(accounts, config.period_start, config.period_end, rng, fake)
            tables_data.append((template, title, gl_data, table_layout))

    # Fallback: ensure at least one table
    if not tables_data:
        if disbursements:
            template = get_template(TableType.CASH_OUT, vendor)
            title = rng.choice(template.title_options)
            tables_data.append((template, title, disbursements, layout_type))
        elif receipts:
            template = get_template(TableType.CASH_IN, vendor)
            title = rng.choice(template.title_options)
            tables_data.append((template, title, receipts, layout_type))

    # Render PDF
    pdf_dir = config.out_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    # Include layout type and orientation in filename for easy identification
    layout_abbrev = layout_type.value[:4].upper()
    orient_abbrev = orientation[0].upper()  # P or L
    pdf_path = pdf_dir / f"{doc_id}_L{degradation_level}_{layout_abbrev}_{orient_abbrev}.pdf"

    renderer = PDFRenderer()
    rendered_tables, non_table_regions, page_count = renderer.render_document(
        doc_id=doc_id,
        pdf_path=pdf_path,
        tables_data=tables_data,
        vendor_system=vendor,
        rng=rng,
        orientation=orientation,
        degradation_level=degradation_level,
    )

    # Write labels (including non-table regions for Model 1)
    counts = write_labels(rendered_tables, config.out_dir, doc_id, non_table_regions)

    # Write document metadata
    write_document_metadata(
        doc_id=doc_id,
        vendor_system=vendor,
        property_type=property_type,
        gl_mask=gl_mask,
        degradation_level=degradation_level,
        pdf_path=pdf_path,
        period_start=config.period_start.isoformat(),
        period_end=config.period_end.isoformat(),
        out_dir=config.out_dir,
    )

    return doc_id, rendered_tables, non_table_regions, page_count


def generate_corpus(config: GeneratorConfig) -> dict:
    """
    Generate the complete corpus of synthetic PDFs and labels.

    Returns summary statistics.
    """
    rng = np.random.default_rng(config.seed)

    # Clear existing labels
    clear_labels(config.out_dir)

    total_tables = 0
    total_non_tables = 0
    total_rows = 0
    total_tokens = 0
    total_pages = 0

    print(f"Generating {config.num_pdfs} documents...")
    print(f"Output directory: {config.out_dir}")

    for doc_idx in range(config.num_pdfs):
        doc_id, rendered_tables, non_table_regions, page_count = generate_document(doc_idx, config, rng)

        # Count labels
        for table in rendered_tables:
            total_tables += 1
            for row in table.rows:
                total_rows += 1
                total_tokens += len([c for c in row.cells if c.text])

        total_non_tables += len(non_table_regions)
        total_pages += page_count

        if (doc_idx + 1) % 10 == 0 or doc_idx == 0:
            print(f"  Generated {doc_idx + 1}/{config.num_pdfs} documents")

    stats = {
        "num_pdfs": config.num_pdfs,
        "total_tables": total_tables,
        "total_non_tables": total_non_tables,
        "total_regions": total_tables + total_non_tables,
        "total_rows": total_rows,
        "total_tokens": total_tokens,
        "total_pages": total_pages,
    }

    print("\nGeneration complete!")
    print(f"  PDFs: {stats['num_pdfs']}")
    print(f"  TABLE regions: {stats['total_tables']}")
    print(f"  NON_TABLE regions: {stats['total_non_tables']}")
    print(f"  Total regions (Model 1): {stats['total_regions']}")
    print(f"  Rows: {stats['total_rows']}")
    print(f"  Tokens: {stats['total_tokens']}")
    print(f"  Pages: {stats['total_pages']}")

    return stats


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="GLASS Synthetic Data Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out"),
        help="Output directory for PDFs and labels",
    )
    parser.add_argument(
        "--num-pdfs",
        type=int,
        help="Number of PDFs to generate (overrides config)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed (overrides config)",
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        config = load_config(args.config)
    else:
        config = GeneratorConfig()

    # Override with CLI args
    if args.out_dir:
        config.out_dir = args.out_dir
    if args.num_pdfs:
        config.num_pdfs = args.num_pdfs
    if args.seed:
        config.seed = args.seed

    # Generate corpus
    generate_corpus(config)


if __name__ == "__main__":
    main()
