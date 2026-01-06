# Challenges

## Challenge 1: PDF Object-Level Construction vs. Visual Mimicry

### The Problem

Initial approach: Generate PDFs that "look like" real financial reports using image composition or template overlays.

**Why this failed:** Models trained on visually similar PDFs didn't generalize. When parsed with pdfplumber/PyMuPDF, the synthetic PDFs had completely different structural properties than real PDFs. The model learned to recognize our generation artifacts, not actual table structure.

### The Root Cause

Real PDF parsers don't see pixels—they see text blocks with coordinates:

```python
# What pdfplumber returns:
[
    (x0, y0, x1, y1, "text_content", block_number, block_type),
    (72.0, 280.5, 220.3, 295.2, "Cash in Bank", 0, 0),
    (449.8, 280.1, 519.7, 295.8, "$45,234.12", 1, 0),
]
```

Key observations from real PDFs:
- Y-coordinates for "same row" differ by 0.4-2.0px
- X-coordinates for "same column" vary by 0.5-1.5px
- Bounding box heights differ even for same font size
- Text encoding has ligatures, Unicode variations, OCR-like artifacts

### The Solution

Reverse-engineer how real PDF generators (ReportLab, PDFsharp, Crystal Reports) construct documents at the object level. Built a ReportLab-based renderer that:

1. Uses canvas-based drawing (not templates)
2. Computes precise bounding boxes with font metrics
3. Applies coordinate noise matching real parsers
4. Generates text-native PDFs (not images)

**Validation:** Models trained on synthetic PDFs now successfully extract real vendor reports (First Service, Lindenwood) with zero real training examples.

---

## Challenge 2: The Circular Feature Problem

### The Problem

Our initial synthetic data included "perfect" metadata as features:

```python
# WRONG: Features generated alongside PDF
features = {'n_rows': 10, 'n_cols': 3, 'has_headers': True}
pdf = generate_pdf(**features)
# Result: 100% accuracy on synthetic, 0% on real
```

The model learned to use features that can only be computed AFTER solving the table detection problem (circular dependency).

### Why This Happened

We had privileged access to generation parameters. Real PDF extraction doesn't know:
- How many rows exist (must cluster y-coordinates with tolerance)
- How many columns exist (must detect alignment patterns)
- Whether headers exist (requires semantic understanding)

### The Solution

Extract features FROM generated PDFs using real parsing:

```python
# CORRECT: Extract features like production pipeline
pdf_bytes = create_pdf_with_noise(n_rows=10, n_cols=3)
blocks = pdfplumber.extract_text_blocks(pdf_bytes)
features = extract_geometric_features(blocks)
# features = {
#   'vertical_alignment_score': 0.3,
#   'numeric_ratio': 0.7,
#   # NO n_rows, n_cols!
# }
```

**Result:** Model accuracy dropped from 100% to 82% on synthetic—but now generalizes to real PDFs (75%+).

---

## Challenge 3: Stratified Curriculum Design (80/20 Split)

### The Problem

Uniform noise distribution produced models that:
- Performed well on "average" documents
- Failed catastrophically on edge cases (heavy degradation, unusual layouts)
- Couldn't handle the long tail of real-world variation

### What We Learned

Real financial PDFs follow a distribution:
- **~70%**: Clean to moderately noisy (modern accounting software)
- **~20%**: Heavily degraded (scanned documents, legacy systems)
- **~10%**: Extreme edge cases (OCR artifacts, encoding issues)

Training on uniform distribution over-fit to the median case.

### The Solution

Implemented stratified curriculum:

| Level | Distribution | Purpose |
|-------|--------------|---------|
| 1 (Clean) | 20% | Baseline performance anchor |
| 2 (Mild) | 25% | Common modern software |
| 3 (Moderate) | 25% | Typical accounting systems |
| 4 (Heavy) | 20% | Scanned/legacy documents |
| 5 (Extreme) | 10% | Edge case robustness |

**Key insight:** The 80/20 nominal/edge-case split mirrors real-world document distribution. Models must see enough edge cases to handle them, but not so many that they over-fit to extreme noise.

---

## Challenge 4: Vendor Style Replication

### The Problem

Financial documents come from 14+ different property management platforms, each with unique visual signatures:

- AKAM: Courier font, full grid
- First Service: Helvetica, alternating rows with blue headers
- Yardi: Compact spacing, minimal grid
- Buildium: Modern styling, thick borders

Initial synthetic data used uniform styling—models couldn't transfer across vendors.

### The Investigation

Forensic analysis of real vendor PDFs revealed:

1. **Grid styles vary systematically** (5 distinct patterns)
2. **Font choices correlate with vendor age** (older = Courier, newer = Helvetica)
3. **Spacing patterns are vendor-specific** (compact vs. expanded)
4. **Color usage differs** (grayscale vs. accent colors)

### The Solution

Created 14 vendor style profiles encoding discovered patterns:

| Vendor | Font | Grid Style | Row Height |
|--------|------|------------|------------|
| AKAM_OLD | Courier | FULL_GRID | 12pt (compact) |
| FIRSTSERVICE | Helvetica | ALTERNATING_ROWS | 16pt |
| YARDI | Helvetica | FULL_GRID | 12pt (compact) |
| APPFOLIO | Helvetica | HORIZONTAL_ONLY | 16pt |

**Result:** Models trained on multi-vendor synthetic data now transfer to unseen vendors (Lindenwood, Douglas) without fine-tuning.

---

## Challenge 5: Multi-Line Cell and Text Wrapping

### The Problem

Long text in narrow columns wraps across multiple lines, creating multiple text blocks for a single logical cell:

```
Visual (1 cell):          Extracted (2 blocks):
  Accumulated Deprec-     Block 1: "Accumulated Deprec-" (y=300)
  iation - Equipment      Block 2: "iation - Equipment" (y=318)
```

This inflates row counts and breaks alignment detection.

### Detection Difficulty

Distinguishing multi-line cells from separate rows requires:
- Vertical proximity analysis (y-delta < threshold)
- Horizontal overlap detection (same x-range)
- Content continuity analysis (hyphenation, punctuation)

Simple "count y-coordinates" approach fails completely.

### The Solution

Implemented multi-line cell simulation in synthetic generation:

```python
def simulate_cell_wrapping(text, col_width):
    if len(text) > max_chars_per_line:
        lines = word_wrap(text, col_width)
        # Each line becomes separate block
        # Adds realistic vertical spacing between lines
        # Occasionally adds hyphenation artifacts
```

**Training signal:** Models now learn to cluster vertically adjacent blocks with horizontal overlap as single logical cells.

---

## Challenge 6: Alignment Detection Without Structure

### The Problem

Column detection seems simple: cluster x-coordinates. But:
- Left-aligned text has consistent x0, variable x1
- Right-aligned text has variable x0, consistent x1
- Center-aligned has variable both
- Intentional indentation mimics column structure

Example ambiguity:
```
Cash in Bank              $45,234.12   # x1=220, x0=450
Accounts Receivable       $12,456.78   # x1=260, x0=450

Is this 2 columns or 4?
```

### The Insight

Must cluster x0 AND x1 separately, then analyze gaps:
- Left-aligned columns: cluster x0, ignore x1
- Right-aligned columns: cluster x1, ignore x0
- Detect "true gaps" (no content in horizontal range)

### The Solution

Implemented alignment-aware clustering:

1. Cluster x0 coordinates (tolerance ±3px)
2. Cluster x1 coordinates separately
3. Detect horizontal gaps > 15px with no overlapping text
4. Infer column structure from gap analysis

Synthetic data now generates realistic alignment patterns:
- First column: 95% left-aligned
- Numeric columns: 85% right-aligned
- Variable column widths (not uniform)

---

## Key Learnings

1. **Match the extraction pipeline, not the visual output**—what matters is how parsers see the document

2. **Features must be derivable from noisy coordinates**—anything requiring solved structure is circular

3. **Curriculum matters**—80/20 nominal/edge-case split mirrors real-world distribution

4. **Vendor diversity drives generalization**—single-style training doesn't transfer

5. **Validate on real documents continuously**—synthetic accuracy can be misleading
