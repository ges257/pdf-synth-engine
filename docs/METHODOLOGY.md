# Synthetic Lab - Production-Grade Synthetic Data Generator

**Date:** December 10, 2025
**Time:** 12:45 AM EST

---

## Executive Summary

This document provides a comprehensive technical specification of the **GLASS Synthetic Data Generator** (Ground-truth Labels for Accounting Statement Structure), a production-grade Python system for generating synthetic CIRA financial statement PDFs with pixel-perfect ground-truth labels for machine learning model training.

**Final Corpus Statistics (5,000 PDFs):**
- 5,000 synthetic PDF documents
- 17,918 labeled regions (10,005 TABLE + 7,913 NON_TABLE)
- 65,885 classified rows
- 473,516 semantic tokens
- 1,493,042 cell-level annotations
- ~760 MB total label data

---

## 1. Project Overview

### 1.1 Purpose

GLASS addresses the fundamental challenge in document AI: obtaining large-scale, precisely-labeled training data for table detection and information extraction. Real-world financial documents require expensive manual annotation and often contain confidential information. This synthetic data generator produces unlimited training samples with perfect ground truth.

### 1.2 Target Models

The system generates labels for three hierarchical classification models:

| Model | Task | Classes | Training Scope |
|-------|------|---------|----------------|
| **Model 1** | Table-Region Detection | TABLE, NON_TABLE | All layouts |
| **Model 2** | Row-Type Classification | HEADER, BODY, SUBTOTAL_TOTAL, NOTE | Cash tables only |
| **Model 3** | Token Semantic Labeling | DATE, VENDOR, ACCOUNT, AMOUNT, OTHER | Cash tables only |

### 1.3 Domain Focus: CIRA Financial Documents

**CIRA** (Common Interest Realty Associations) includes:
- **Condominiums** (50.8% of corpus)
- **Homeowners Associations / HOAs** (29.3%)
- **Cooperative Housing / Co-ops** (10.0%)
- **Mixed-Use Developments** (9.9%)

These entities produce standardized financial statements (cash disbursements, receipts, budgets, aging reports) that share common structural patterns while varying in visual presentation across property management software vendors.

---

## 2. System Architecture

### 2.1 Directory Structure

```
/home/g12/glass_syn_data/
├── glass_synth/                    # Core Python package (12 modules)
│   ├── __init__.py                 # Package version (0.1.0)
│   ├── cli.py                      # CLI entry point & orchestration
│   ├── config.py                   # Configuration dataclasses
│   ├── chart_of_accounts.py        # GL account generation
│   ├── ledger_generator.py         # Transaction synthesis
│   ├── table_templates.py          # Table schema definitions
│   ├── vendor_styles.py            # 14 vendor visual profiles
│   ├── layout_engine.py            # Page layout computation
│   ├── pdf_renderer.py             # ReportLab PDF generation (57KB)
│   ├── degradation.py              # 5-level quality degradation
│   ├── labels_writer.py            # JSONL serialization
│   └── non_table_regions.py        # Non-table content generation
├── configs/
│   └── small_test.yml              # Configuration templates
├── data/                           # Static data assets
├── out/                            # Generated outputs
│   ├── pdfs/                       # 5,000 PDF files (~40 MB)
│   └── labels/                     # JSONL label files (~720 MB)
│       ├── model1_regions.jsonl    # 7.8 MB - region detection
│       ├── model2_rows.jsonl       # 21.1 MB - row classification
│       ├── model3_tokens.jsonl     # 163.5 MB - token semantics
│       ├── cells.jsonl             # 523 MB - cell-level ground truth
│       ├── documents.jsonl         # 1.3 MB - document metadata
│       └── corpus_statistics.txt   # Summary statistics
└── .venv/                          # Python virtual environment
```

### 2.2 Module Responsibilities

| Module | Lines | Primary Responsibility |
|--------|-------|------------------------|
| `pdf_renderer.py` | ~1,200 | Core PDF generation with ReportLab; handles all 5 layout types |
| `cli.py` | ~400 | Document generation orchestration; sampling logic |
| `table_templates.py` | ~350 | 6 table type schemas; column specifications |
| `vendor_styles.py` | ~300 | 14 vendor visual profiles; grid styles |
| `layout_engine.py` | ~250 | Page layout computation; bbox calculation |
| `degradation.py` | ~200 | Parametric degradation engine |
| `ledger_generator.py` | ~180 | Financial transaction synthesis |
| `chart_of_accounts.py` | ~150 | GL code generation; CIRA accounting |
| `labels_writer.py` | ~230 | 5 JSONL output formats |
| `non_table_regions.py` | ~150 | Non-table region generation |
| `config.py` | ~135 | YAML configuration loading |

### 2.3 Data Flow Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GENERATION PIPELINE                         │
└─────────────────────────────────────────────────────────────────────┘

1. CONFIGURATION
   ├── Load YAML config or use defaults
   ├── Parse distributions (table_mix, vendor, property_type, etc.)
   └── Initialize RNG with seed for reproducibility

2. PER-DOCUMENT SAMPLING
   ├── Sample: vendor_system, property_type, gl_mask, degradation_level
   ├── Sample: layout_type, orientation (portrait/landscape)
   └── Generate doc_id: {vendor}__{index:05d}__{period}

3. FINANCIAL DATA GENERATION
   ├── Build chart of accounts (GL codes per mask format)
   ├── Generate journal entries (balanced debits/credits)
   └── Generate cash transactions (disbursements + receipts)

4. TABLE CONSTRUCTION (1-3 per document)
   ├── Sample table_type (CASH_OUT, CASH_IN, BUDGET, UNPAID, AGING, GL)
   ├── Get template with column specs for vendor
   ├── Generate table data from transactions or random dicts
   └── Apply column header synonyms (Date→Trans Date, etc.)

5. PDF RENDERING
   ├── Create ReportLab canvas (portrait: 612×792pt, landscape: 792×612pt)
   ├── Apply vendor style (font, colors, grid pattern)
   ├── Generate non-table regions (headers, footers, notes)
   ├── Render tables per layout type:
   │   ├── HORIZONTAL_LEDGER: Standard row-based table
   │   ├── SPLIT_LEDGER: Two side-by-side tables
   │   ├── VERTICAL_KV: Key-value form layout
   │   ├── MATRIX: Cross-tab budget view
   │   └── RAGGED: Misaligned pseudo-table
   ├── Apply degradation (jitter, missing lines, font variation)
   └── Save PDF to out/pdfs/

6. LABEL SERIALIZATION
   ├── model1_regions.jsonl: All TABLE + NON_TABLE regions
   ├── model2_rows.jsonl: Row types (cash + valid layouts only)
   ├── model3_tokens.jsonl: Token semantics (cash + valid layouts only)
   ├── cells.jsonl: All cells from all tables (Appendix D.2)
   └── documents.jsonl: Document-level metadata
```

---

## 3. Technical Implementation Details

### 3.1 PDF Generation (ReportLab)

**Rendering Approach:**
- Canvas-based direct drawing (not flowables)
- Coordinate system: (0,0) at bottom-left, Y increases upward
- Page dimensions: 8.5" × 11" (612 × 792 points)
- Default margins: 0.5" (36 points)

**Text Handling:**
- Binary search truncation algorithm for cell overflow
- Ellipsis ("...") appended to truncated text
- Right-alignment for numeric columns (AMOUNT)
- Font metrics via `stringWidth()` for precise placement

**Grid Rendering:**
- 5 distinct grid styles per vendor
- Degradation-aware line skipping (probability-based)
- Position jitter applied to line endpoints

### 3.2 Layout Types

| Layout | Proportion | Rendering Method | Key Characteristics |
|--------|------------|------------------|---------------------|
| **HORIZONTAL_LEDGER** | 70.8% | `_render_table()` | Standard row-based; full-width columns |
| **MATRIX_BUDGET** | 18.1% | `_render_matrix()` | GL × Period cross-tab; aggregated values |
| **SPLIT_LEDGER** | 4.2% | `_render_table()` × 2 | Two tables side-by-side; 20pt gap |
| **RAGGED_PSEUDOTABLE** | 3.5% | `_render_ragged()` | Intentional misalignment; variable jitter |
| **VERTICAL_KEY_VALUE** | 3.4% | `_render_vertical_kv()` | Stacked label/value pairs; max 3 txns |

**Model Training Scope:**
- Model 1: ALL layouts (learns table vs non-table)
- Models 2-3: Only HORIZONTAL_LEDGER + SPLIT_LEDGER (canonical cash table structure)

### 3.3 Table Types and Schemas

**Six Financial Statement Types:**

| Type | Description | Columns | Row Count |
|------|-------------|---------|-----------|
| **CASH_OUT** | Schedule B - Disbursements | Date, Vendor, GL Code, Description, Check #, Amount, Balance | 15-60 |
| **CASH_IN** | Schedule D - Receipts | Date, Unit, Owner, GL Code, Description, Receipt #, Amount, Balance | 10-40 |
| **BUDGET** | Income Statement | Account, Current, YTD Actual, YTD Budget, Annual Budget, Variance | 20-80 |
| **UNPAID** | Open Payables | Date, Vendor, Invoice #, Due Date, GL Code, Description, Amount | 10-40 |
| **AGING** | AR Aging | Unit, Owner, Current, 30 Days, 60 Days, 90 Days, 90+ Days, Total | 15-60 |
| **GL** | General Ledger | Date, Reference, Description, Debit, Credit, Balance, GL Code | 20-100 |

**Column Header Synonyms (per Section 3.3 of spec):**
```
DATE:    Date, Trans Date, Transaction Date, Posting Date, Post Date
VENDOR:  Vendor, Payee, Paid To, Name, Description
CHECK:   Check #, Check No, Chk #, Reference, Ref #
AMOUNT:  Amount, Paid, Total, Payment
GL_CODE: GL Code, Account #, Acct #, GL #, Account
```

### 3.4 Vendor Visual Styles

**14 Property Management Software Styles:**

| Vendor | Font | Grid Style | Header Color | Row Height | Compact |
|--------|------|------------|--------------|------------|---------|
| AKAM_OLD | Courier | FULL_GRID | #D0D0D0 | 12.0pt | Yes |
| AKAM_NEW | Helvetica | HORIZONTAL_ONLY | #E8E8E8 | 14.0pt | No |
| DOUGLAS | Times-Roman | BOX_BORDERS | #F0F0F0 | 14.0pt | No |
| FIRSTSERVICE | Helvetica | ALTERNATING_ROWS | #2C5282 | 16.0pt | No |
| LINDENWOOD | Helvetica | MINIMAL | #FFFFFF | 14.0pt | No |
| YARDI | Helvetica | FULL_GRID | #EEEEEE | 12.0pt | Yes |
| APPFOLIO | Helvetica | HORIZONTAL_ONLY | #FFFFFF | 16.0pt | No |
| BUILDIUM | Helvetica | ALTERNATING_ROWS | #4A5568 | 14.0pt | No |
| MDS | Courier | FULL_GRID | #CCCCCC | 11.0pt | Yes |
| CINC | Helvetica | MINIMAL | #F5F5F5 | 14.0pt | No |
| OTHER_1-4 | Mixed | Mixed | Mixed | 13-15pt | Mixed |

**Grid Style Definitions:**
- **FULL_GRID**: All horizontal + vertical lines
- **HORIZONTAL_ONLY**: Row separator lines only
- **MINIMAL**: Header/footer lines only
- **ALTERNATING_ROWS**: Zebra striping (no vertical lines)
- **BOX_BORDERS**: Outer border + header separator

### 3.5 Degradation Engine

**5-Level Parametric Degradation:**

| Parameter | Level 1 (Clean) | Level 3 (Moderate) | Level 5 (Extreme) |
|-----------|-----------------|--------------------|--------------------|
| Position Jitter | 0.0 pt | 2.0 pt | 5.0 pt |
| Font Size Range | 1.0× | 0.90-1.10× | 0.80-1.25× |
| Grid Line Probability | 100% | 85% | 50% |
| Row Height Range | 1.0× | 0.90-1.10× | 0.75-1.30× |
| Cell Padding Range | 1.0× | 0.80-1.20× | 0.40-1.60× |
| Column Width Variation | 0% | 8% | 18% |
| Alignment Jitter | 0% | 5% | 15% |
| Character Spacing | 0% | 2% | 5% |

**Degradation Methods:**
- `apply_position_jitter()`: Adds random offset to (x, y) coordinates
- `should_draw_grid_line()`: Probabilistically skips grid lines
- `apply_font_size_variation()`: Multiplies base font size
- `apply_row_height_variation()`: Varies row spacing
- `should_misalign()`: Randomly changes text alignment

### 3.6 Chart of Accounts Structure

**GL Code Formats (4 mask types):**
```
NNNN:       4-digit      e.g., 6015
NNNNN:      5-digit      e.g., 06015
NN-NNNN-NN: fund-code    e.g., 01-6015-00
NNNNNN:     6-digit      e.g., 016015
```

**Account Ranges:**
- Revenue: 4000-4999 (assessments, late fees, interest, parking, other)
- Expenses: 6000-9000 (management, legal, insurance, utilities, maintenance)
- Reserves: 3000-3199 (roof, elevator, painting)

**Fund Codes:**
- 01: Operating Fund
- 02: Reserve Fund
- 03: Special Assessment Fund
- 04: Payroll Fund

### 3.7 Transaction Generation

**Log-Normal Distribution for Realistic Amounts:**

| Category | Min | Max | Distribution |
|----------|-----|-----|--------------|
| Administrative | $500 | $5,000 | Log-normal (μ=log(2750), σ=0.5) |
| Legal Fees | $1,000 | $15,000 | Log-normal (μ=log(8000), σ=0.5) |
| Insurance | $2,000 | $20,000 | Log-normal (μ=log(11000), σ=0.5) |
| Utilities | $200 | $3,000 | Log-normal (μ=log(1600), σ=0.4) |
| Maintenance | $100 | $5,000 | Log-normal (μ=log(2550), σ=0.4) |
| Assessments | $500 | $5,000 | Log-normal (μ=log(2750), σ=0.4) |

**Transaction Split:** 70% expenses (CASH_OUT), 30% revenue (CASH_IN)

---

## 4. Ground-Truth Label Schemas

### 4.1 Model 1: Region Detection (model1_regions.jsonl)

```json
{
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "doc_id": "BUILDIUM__00000__2025-01",
  "page_index": 1,
  "bbox": [36, -129.8, 756.0, 576.0],
  "table_type": "CASH_OUT",
  "layout_type": "horizontal_ledger",
  "is_table_region": true,
  "vendor_system": "BUILDIUM",
  "title_text": "Paid Items",
  "fund": "OPERATING",
  "n_rows": 48,
  "n_cols": 7,
  "column_headers": ["Trans Date", "Paid To", "Acct #", ...],
  "orientation": "landscape"
}
```

### 4.2 Model 2: Row Classification (model2_rows.jsonl)

```json
{
  "row_id": "BUILDIUM__00000__2025-01__p1_t0_r0",
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "doc_id": "BUILDIUM__00000__2025-01",
  "page_index": 1,
  "row_index": 0,
  "bbox": [36, 538.2, 756.0, 555.0],
  "row_type": "HEADER",
  "is_cash_table": true,
  "layout_type": "horizontal_ledger",
  "table_type": "CASH_OUT",
  "n_cols": 7
}
```

### 4.3 Model 3: Token Semantics (model3_tokens.jsonl)

```json
{
  "token_id": "BUILDIUM__00000__2025-01__p1_t0_r1_tok0",
  "row_id": "BUILDIUM__00000__2025-01__p1_t0_r1",
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "doc_id": "BUILDIUM__00000__2025-01",
  "page_index": 1,
  "row_index": 1,
  "col_index": 0,
  "text": "03/15/25",
  "bbox": [36, 520.4, 100.8, 537.2],
  "semantic_label": "DATE",
  "row_type": "BODY"
}
```

### 4.4 Cell-Level Ground Truth (cells.jsonl) - Per Appendix D.2

```json
{
  "cell_id": "BUILDIUM__00000__2025-01__p1_t0_r1_c0",
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "doc_id": "BUILDIUM__00000__2025-01",
  "page_index": 1,
  "row_index": 1,
  "col_index": 0,
  "col_semantic": "DATE",
  "row_type": "BODY",
  "bbox": [36, 520.4, 100.8, 537.2],
  "text": "03/15/25",
  "table_type": "CASH_OUT",
  "layout_type": "horizontal_ledger"
}
```

### 4.5 Document Metadata (documents.jsonl)

```json
{
  "doc_id": "BUILDIUM__00000__2025-01",
  "vendor_system": "BUILDIUM",
  "property_type": "CONDO",
  "fiscal_period_start": "2025-01-01",
  "fiscal_period_end": "2025-12-31",
  "gl_mask": "NN-NNNN-NN",
  "degradation_level": 3,
  "pdf_path": "out/pdfs/BUILDIUM__00000__2025-01_L3_HORI_L.pdf"
}
```

---

## 5. Final Corpus Statistics

### 5.1 Document Distribution

| Metric | Count | Percentage |
|--------|-------|------------|
| **Total PDFs** | 5,000 | 100% |
| FIRSTSERVICE | 523 | 10.5% |
| BUILDIUM | 520 | 10.4% |
| AKAM_NEW | 512 | 10.2% |
| AKAM_OLD | 512 | 10.2% |
| LINDENWOOD | 509 | 10.2% |
| YARDI | 503 | 10.1% |
| OTHER | 496 | 9.9% |
| APPFOLIO | 484 | 9.7% |
| DOUGLAS | 469 | 9.4% |
| CINC | 237 | 4.7% |
| MDS | 235 | 4.7% |

### 5.2 Property Type Distribution

| Type | Count | Percentage |
|------|-------|------------|
| CONDO | 2,538 | 50.8% |
| HOA | 1,467 | 29.3% |
| COOP | 502 | 10.0% |
| MIXED_USE | 493 | 9.9% |

### 5.3 Degradation Level Distribution

| Level | Count | Percentage | Description |
|-------|-------|------------|-------------|
| Level 1 | 972 | 19.4% | Clean |
| Level 2 | 1,323 | 26.5% | Mild |
| Level 3 | 1,262 | 25.2% | Moderate |
| Level 4 | 961 | 19.2% | Heavy |
| Level 5 | 482 | 9.6% | Extreme |

### 5.4 Region Statistics (Model 1)

| Metric | Count |
|--------|-------|
| **Total Regions** | 17,918 |
| TABLE regions | 10,005 (55.8%) |
| NON_TABLE regions | 7,913 (44.2%) |

### 5.5 Table Type Distribution

| Type | Count | Percentage |
|------|-------|------------|
| BUDGET | 2,224 | 22.2% |
| CASH_IN | 1,761 | 17.6% |
| CASH_OUT | 1,749 | 17.5% |
| GL | 1,706 | 17.1% |
| AGING | 1,291 | 12.9% |
| UNPAID | 1,274 | 12.7% |

### 5.6 Layout Type Distribution

| Layout | Count | Percentage |
|--------|-------|------------|
| horizontal_ledger | 7,080 | 70.8% |
| matrix_budget | 1,810 | 18.1% |
| split_ledger | 423 | 4.2% |
| ragged_pseudotable | 348 | 3.5% |
| vertical_key_value | 344 | 3.4% |

### 5.7 Row Statistics (Model 2)

| Row Type | Count | Percentage |
|----------|-------|------------|
| **Total Rows** | 65,885 | 100% |
| BODY | 61,293 | 93.0% |
| HEADER | 2,296 | 3.5% |
| SUBTOTAL_TOTAL | 2,296 | 3.5% |

### 5.8 Token Statistics (Model 3)

| Semantic Label | Count | Percentage |
|----------------|-------|------------|
| **Total Tokens** | 473,516 | 100% |
| AMOUNT | 131,770 | 27.8% |
| OTHER | 127,178 | 26.9% |
| VENDOR | 87,390 | 18.5% |
| DATE | 63,589 | 13.4% |
| ACCOUNT | 63,589 | 13.4% |

### 5.9 Cell Statistics

| Metric | Count |
|--------|-------|
| **Total Cells** | 1,493,042 |

### 5.10 File Sizes

| File | Size |
|------|------|
| cells.jsonl | 523.0 MB |
| model3_tokens.jsonl | 163.5 MB |
| model2_rows.jsonl | 21.1 MB |
| model1_regions.jsonl | 7.8 MB |
| documents.jsonl | 1.3 MB |
| **Total Labels** | ~717 MB |
| PDFs (5,000 files) | ~40 MB |

---

## 6. Key Design Decisions

### 6.1 Separation of Generator Internals from Training Features

**Critical Principle:** Generator metadata (cell_id, col_index, layout_type, template name) is used **only for label generation**, never as model input features.

**Training Features (X):** Only what pdfplumber extracts from real PDFs:
- Token text
- Bounding box coordinates (x0, y0, x1, y1)
- Page index
- Local context (row height, column densities)

**Labels (Y):** Derived from generator's privileged knowledge:
- is_table_region (Model 1)
- row_type (Model 2)
- semantic_label (Model 3)

### 6.2 Layout-Specific Model Training

Models 2 and 3 only train on HORIZONTAL_LEDGER and SPLIT_LEDGER layouts because:
1. These are the canonical cash table structures with clear row/column semantics
2. VERTICAL_KV, MATRIX, and RAGGED layouts have different structural patterns
3. Model 1 still learns from ALL layouts to distinguish tables from non-tables

### 6.3 Text-Native PDFs

All generated PDFs are **text-native** (not images), ensuring:
- Direct text extraction via pdfplumber without OCR
- Precise bounding box alignment between rendered content and labels
- Faster processing during model training

### 6.4 Reproducibility

- Deterministic generation via configurable seed
- Same seed + config produces identical corpus
- Enables reproducible experiments and ablation studies

---

## 7. Dependencies and Environment

### 7.1 Python Dependencies

```
numpy          # Random sampling, log-normal distributions
faker          # Realistic names, addresses, companies
reportlab      # PDF generation
pdfplumber     # PDF text extraction (validation)
pyyaml         # Configuration loading
```

### 7.2 Runtime Environment

- Python 3.10+
- Virtual environment: `.venv/`
- Activation: `source .venv/bin/activate`
- Execution: `python -m glass_synth.cli --num-pdfs 5000 --seed 42 --out-dir out`

---

## 8. Research Paper Reference Points

### 8.1 Novel Contributions

1. **Multi-Layout Synthetic Generation**: 5 distinct table layouts covering real-world variation
2. **Parametric Degradation**: 5-level degradation simulating OCR challenges
3. **Hierarchical Ground Truth**: Region → Row → Token → Cell annotation hierarchy
4. **Domain-Specific Realism**: CIRA-compliant financial semantics
5. **Scalable Generation**: Configuration-driven corpus size with reproducibility

### 8.2 Evaluation Metrics

- Model 1: Region IoU, precision/recall for TABLE vs NON_TABLE
- Model 2: Row-type classification accuracy, confusion matrix
- Model 3: Token semantic F1 per class (DATE, VENDOR, ACCOUNT, AMOUNT, OTHER)

### 8.3 Ablation Studies Enabled

- Layout type impact on model generalization
- Degradation level robustness
- Vendor style transfer learning
- Column synonym variation effects

---

## 9. Future Extensions

1. **Multi-language support**: Column headers in Spanish, French, etc.
2. **Additional table types**: Trial balance, bank reconciliation
3. **Image degradation**: Scan artifacts, rotation, blur
4. **Handwritten annotations**: Simulated manual marks
5. **Multi-document linking**: Related statements across periods

---

## Appendix A: Configuration Schema

```yaml
num_pdfs: 5000
seed: 42
period_start: "2025-01-01"
period_end: "2025-12-31"
out_dir: "out"

table_mix:
  CASH_OUT: [0.15, 0.20]
  CASH_IN: [0.15, 0.20]
  BUDGET: [0.20, 0.25]
  UNPAID: [0.10, 0.15]
  AGING: [0.10, 0.15]
  GL: [0.15, 0.20]

vendor_distribution:
  AKAM_OLD: 0.10
  AKAM_NEW: 0.10
  DOUGLAS: 0.10
  FIRSTSERVICE: 0.10
  LINDENWOOD: 0.10
  YARDI: 0.10
  APPFOLIO: 0.10
  BUILDIUM: 0.10
  MDS: 0.05
  CINC: 0.05
  OTHER: 0.10

property_type_distribution:
  CONDO: 0.50
  HOA: 0.30
  COOP: 0.10
  MIXED_USE: 0.10

gl_mask_distribution:
  "NNNN": 0.30
  "NNNNN": 0.30
  "NN-NNNN-NN": 0.30
  "NNNNNN": 0.10

degradation_distribution:
  1: 0.20
  2: 0.25
  3: 0.25
  4: 0.20
  5: 0.10

layout_distribution:
  horizontal_ledger: 0.55
  split_ledger: 0.10
  vertical_key_value: 0.10
  matrix_budget: 0.15
  ragged_pseudotable: 0.10

orientation_distribution:
  portrait: 0.60
  landscape: 0.40
```

---

## Appendix B: CLI Usage

```bash
# Generate full corpus
python -m glass_synth.cli --num-pdfs 5000 --seed 42 --out-dir out

# Quick test run
python -m glass_synth.cli --num-pdfs 10 --seed 42 --out-dir test_out

# With custom config
python -m glass_synth.cli --config configs/custom.yml
```

---

*Document generated: December 10, 2025 at 12:45 AM EST*
*GLASS Synthetic Data Generator v0.1.0*
