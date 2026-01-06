# Output Files

This directory contains generated PDFs and ground-truth labels.

## Directory Structure

```
outputs/
├── pdfs/               # Generated PDF files
└── labels/             # Ground-truth label files
    ├── model1_regions.jsonl    # TABLE vs NON_TABLE regions
    ├── model2_rows.jsonl       # Row type classification
    ├── model3_tokens.jsonl     # Token semantic labels
    ├── cells.jsonl             # Cell-level ground truth
    └── documents.jsonl         # Document metadata
```

## Label File Formats

### model1_regions.jsonl

Region-level labels for table detection (Model 1):

```json
{
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "doc_id": "BUILDIUM__00000__2025-01",
  "page_index": 1,
  "bbox": [36, 129.8, 756.0, 576.0],
  "table_type": "CASH_OUT",
  "layout_type": "horizontal_ledger",
  "is_table_region": true
}
```

### model2_rows.jsonl

Row-level labels for row classification (Model 2):

```json
{
  "row_id": "BUILDIUM__00000__2025-01__p1_t0_r0",
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "row_index": 0,
  "bbox": [36, 538.2, 756.0, 555.0],
  "row_type": "HEADER"
}
```

### model3_tokens.jsonl

Token-level labels for semantic classification (Model 3):

```json
{
  "token_id": "BUILDIUM__00000__2025-01__p1_t0_r1_tok0",
  "row_id": "BUILDIUM__00000__2025-01__p1_t0_r1",
  "col_index": 0,
  "text": "03/15/25",
  "bbox": [36, 520.4, 100.8, 537.2],
  "semantic_label": "DATE"
}
```

### cells.jsonl

Cell-level ground truth (full detail):

```json
{
  "cell_id": "BUILDIUM__00000__2025-01__p1_t0_r1_c0",
  "table_id": "BUILDIUM__00000__2025-01__p1_t0",
  "row_index": 1,
  "col_index": 0,
  "col_semantic": "DATE",
  "row_type": "BODY",
  "bbox": [36, 520.4, 100.8, 537.2],
  "text": "03/15/25"
}
```

### documents.jsonl

Document-level metadata:

```json
{
  "doc_id": "BUILDIUM__00000__2025-01",
  "vendor_system": "BUILDIUM",
  "property_type": "CONDO",
  "degradation_level": 3,
  "pdf_path": "pdfs/BUILDIUM__00000__2025-01_L3_HORI_L.pdf"
}
```

## Usage

Generated files are not committed to git (see .gitignore). To generate:

```bash
python -m glass_synth.cli --num-pdfs 5000 --seed 42 --out-dir outputs/
```
