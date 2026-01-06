![Header](https://capsule-render.vercel.app/api?type=rect&color=0D1B2A&height=100&text=Synthetic%20Data%20Engine&fontSize=36&fontColor=A78BFA)

<div align="center">

**Reverse-Engineered PDF Reports for [GLASS Table Extraction System](https://github.com/ges257/glass-extraction)**

![Python](https://img.shields.io/badge/Python-3.10+-A3B8CC?style=flat-square)
![ReportLab](https://img.shields.io/badge/ReportLab-PDF_Generation-A3B8CC?style=flat-square)
![Synthetic Data](https://img.shields.io/badge/Synthetic_Data-ML_Training-A78BFA?style=flat-square)

</div>

---

## Outcome

Generated 50,000+ structurally accurate synthetic financial reports. Validated via successful model transfer from purely synthetic training to real-world production documents, effectively bypassing strict vendor privacy constraints that prevented access to proprietary financial data.

## Technical Build

Reverse-engineered PDF construction mechanisms by analyzing technical documentation of source reporting platforms and conducting forensic audits of existing documents. Built a generative pipeline that replicates how these systems construct PDFs at the object level—not just visual appearance—ensuring synthetic outputs match the structural parsing behavior of real reports. Implemented multi-level noise injection (layout, formatting, content) within a stratified curriculum (80% nominal, 20% edge-cases).

---

## The Core Mechanism

```
Forensic Analysis → Template Encoding → Noise Injection → Ground Truth
```

| Stage | Input | Output |
|-------|-------|--------|
| Platform Analysis | Real vendor PDFs | Structural patterns |
| Template Encoding | Patterns | 14 vendor profiles, 5 layouts |
| Noise Injection | Clean templates | 5 degradation levels |
| Ground Truth | Rendered PDFs | Pixel-perfect labels |

---

## Four-Stage Pipeline

```
+------------------------------------------------------------+
|  STAGE 1: FORENSIC ANALYSIS                                 |
|  Target: 14 property management platforms                   |
|  Output: Grid styles, fonts, spacing patterns               |
+------------------------------------------------------------+
                         |
                         v
+------------------------------------------------------------+
|  STAGE 2: TEMPLATE ENCODING                                 |
|  Task: Encode platform-specific rendering rules             |
|  Output: 14 vendor styles, 6 table types, 5 layouts        |
+------------------------------------------------------------+
                         |
                         v
+------------------------------------------------------------+
|  STAGE 3: NOISE INJECTION                                   |
|  Task: Apply stratified degradation curriculum              |
|  Distribution: 80% nominal (L1-L3), 20% edge-case (L4-L5)  |
+------------------------------------------------------------+
                         |
                         v
+------------------------------------------------------------+
|  STAGE 4: GROUND TRUTH GENERATION                           |
|  Output: 5 JSONL label files (~760 MB)                     |
|  Hierarchy: Region -> Row -> Token -> Cell                 |
+------------------------------------------------------------+
```

---

## Degradation Levels

| Level | Position Jitter | Font Variation | Grid Lines | Curriculum |
|-------|-----------------|----------------|------------|------------|
| 1 Clean | 0.0 pt | 1.0x | 100% | 20% |
| 2 Mild | 1.0 pt | 0.95-1.05x | 95% | 25% |
| 3 Moderate | 2.0 pt | 0.90-1.10x | 85% | 25% |
| 4 Heavy | 3.5 pt | 0.85-1.15x | 70% | 20% |
| 5 Extreme | 5.0 pt | 0.80-1.25x | 50% | 10% |

---

## Validation

Synthetic data was used to train GLASS extraction models:

| Metric | Value |
|--------|-------|
| Model Transfer | Synthetic to Production |
| Table Detection Accuracy | 97%+ |
| Row Classification | 99.3% |
| Corpus Size | 50,000+ PDFs |
| Label Data | 760 MB |

**Critical validation:** Models trained exclusively on synthetic data successfully extracted real-world financial documents with zero real training examples.

---

## Project Structure

```
pdf-synth-engine/
├── src/
│   └── glass_synth/
│       ├── pdf_renderer.py           # ReportLab PDF construction
│       ├── layout_engine.py          # Bbox computation
│       ├── degradation.py            # 5-level noise injection
│       ├── ledger_generator.py       # Accounting data synthesis
│       ├── table_templates.py        # 6 table types, 13 semantic types
│       ├── vendor_styles.py          # 14 vendor profiles
│       ├── cli.py                    # Orchestration
│       ├── config.py                 # YAML configuration
│       ├── labels_writer.py          # Ground-truth generation
│       ├── chart_of_accounts.py      # GL codes
│       └── non_table_regions.py      # Non-table regions
├── configs/
│   └── default.yml                   # Generation configuration
├── docs/
│   └── METHODOLOGY.md                # Full pipeline documentation
└── outputs/                          # Generated PDFs and labels
```

---

## Usage

```bash
# Generate synthetic corpus
python -m glass_synth.cli --num-pdfs 5000 --seed 42 --out-dir outputs/

# Quick test run
python -m glass_synth.cli --num-pdfs 10 --seed 42 --out-dir test_out/

# With custom config
python -m glass_synth.cli --config configs/default.yml
```

---

## License

MIT

---

<div align="center">

**Part of the GLASS Document Intelligence System**

[GLASS Extraction](https://github.com/ges257/glass-extraction) | [Profile](https://github.com/ges257)

</div>
