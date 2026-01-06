# Learnings

## Trade-off 1: Rule-Based vs. ML-Based Noise Injection

### The Decision

How to generate realistic noise: learned generative model (GANs, VAEs) or parameterized rule-based system?

### Analysis

**ML-based (considered, rejected):**
- Pros: Could learn complex noise patterns from real PDFs
- Cons: Requires labeled real data (chicken-and-egg problem), introduces second model to debug, black-box noise patterns

**Rule-based (chosen):**
- Pros: Interpretable, debuggable, controllable, no training data needed
- Cons: Manual parameter tuning, may miss subtle patterns

### Why Rule-Based Won

1. **Interpretability matters for debugging:** When model fails on real PDF, need to understand which noise dimension caused it. With rule-based system, can trace back to specific parameter.

2. **Controllable curriculum:** Can explicitly set 80/20 nominal/edge-case split. ML-based would learn its own distribution.

3. **No labeled real data required:** The whole point is to avoid needing real labeled data. Using ML for noise injection would require real PDFs.

4. **Faster iteration:** Changing a noise parameter takes seconds. Retraining a generative model takes hours.

### Implementation

5 degradation levels with 8 parameters each:
- Position jitter (σ = 0-5px)
- Font size variation (0.8x-1.25x)
- Grid line probability (50-100%)
- Row height variation
- Cell padding variation
- Column width variation
- Alignment jitter
- Character spacing

---

## Trade-off 2: Extraction Parity vs. Generation Efficiency

### The Decision

Should synthetic data features be computed FROM generated PDFs (extraction parity) or alongside generation (efficiency)?

### The Temptation

Computing features alongside generation is 10x faster—no need to parse the PDF we just created. We already know the exact structure.

### Why Extraction Parity is Non-Negotiable

**The Circular Feature Problem:**

```python
# Fast but useless:
features = {'n_rows': 10, 'n_cols': 3}  # We know this!
pdf = generate(features)

# Slow but correct:
pdf = generate(n_rows=10, n_cols=3)
blocks = pdfplumber.parse(pdf)  # Extra step
features = extract_from_blocks(blocks)  # What real pipeline sees
```

The entire point of synthetic data is to train models that work on real PDFs. If training features don't match inference features, the model learns the wrong function.

### Result

10x slower generation, but models actually generalize. The first approach produced 100% synthetic accuracy, 0% real accuracy. After extraction parity: 82% synthetic, 75%+ real.

**Lesson:** There are no shortcuts to feature parity. The training pipeline must match the inference pipeline exactly.

---

## Trade-off 3: Single-Model vs. Hierarchical Detection

### The Decision

Train one model to detect tables directly, or a hierarchy of specialized models?

### Analysis

**Single model:**
- Input: Raw PDF page
- Output: Table bounding boxes
- Pro: Simpler pipeline
- Con: Conflates multiple tasks (region detection, row parsing, token classification)

**Hierarchical (chosen):**
- Model 1: TABLE vs NON_TABLE regions
- Model 2: Row type classification (HEADER, BODY, SUBTOTAL, NOTE)
- Model 3: Token semantic labeling (DATE, VENDOR, AMOUNT, etc.)

### Why Hierarchical Won

1. **Different layouts need different treatment:**
   - Model 1 trains on ALL layouts (learns table vs non-table)
   - Models 2-3 train only on HORIZONTAL_LEDGER + SPLIT_LEDGER (canonical structure)
   - VERTICAL_KV, MATRIX, RAGGED have different row semantics

2. **Easier debugging:**
   - If extraction fails, can identify which stage broke
   - Single model: black box failure mode

3. **Incremental improvement:**
   - Can improve row classification without retraining region detection
   - Can add Model 4 (cell merging) later

4. **Ground truth generation:**
   - Easier to generate hierarchical labels
   - Single model would need complex output format

### Label Hierarchy

```
Document
└── Region (Model 1)
    └── Row (Model 2)
        └── Token (Model 3)
            └── Cell (ground truth)
```

---

## Discovery 1: Parsing-Based Validation is Critical

### The Discovery

Early synthetic data looked visually correct but had structural issues only visible through parsing.

### Example

Generated PDF appeared to have aligned columns. But pdfplumber extraction revealed:

```python
# Expected: 3 columns
# Actual: 5 vertical clusters due to text wrapping artifacts
```

Visual inspection passed. Automated validation caught the bug.

### Implementation

Every synthetic PDF now goes through validation pipeline:

1. Generate PDF with known structure (ground truth)
2. Parse with pdfplumber (same as production)
3. Compute features from parsed blocks
4. Compare feature distributions to expectations
5. Flag PDFs with anomalies

```python
def validate_synthetic_pdf(pdf_bytes, expected_structure):
    blocks = pdfplumber.extract(pdf_bytes)
    features = compute_features(blocks)

    # Check alignment cluster count
    assert features['vertical_cluster_count'] <= expected_structure['n_cols'] * 1.5

    # Check numeric ratio for financial tables
    assert features['numeric_ratio'] > 0.3

    # Check spacing distribution
    assert features['row_spacing_std'] < 10.0  # Not too irregular
```

**Lesson:** Visual inspection is necessary but not sufficient. Automated parsing-based validation catches bugs humans miss.

---

## Discovery 2: Vendor Forensics Reveals Hidden Patterns

### The Discovery

Different property management platforms have systematic (not random) visual differences that affect extraction.

### Investigation Method

1. Collected 50+ real PDFs from known vendors
2. Extracted all text blocks with coordinates
3. Analyzed distributions: font choices, spacing patterns, grid styles
4. Clustered vendors by visual signature

### Key Findings

**Grid styles are vendor-specific:**
- AKAM: Full grid (all horizontal + vertical lines)
- First Service: Alternating row backgrounds (zebra striping)
- Yardi: Horizontal lines only
- Buildium: Box borders (outer border + header separator)

**Font choices correlate with vendor age:**
- Legacy systems (pre-2010): Courier, monospace assumptions
- Modern systems (post-2015): Helvetica, variable-width fonts

**Spacing is culturally determined:**
- AKAM (New York): Compact, space-efficient
- First Service (national): Generous spacing, readability focus

### Application

Created 14 vendor profiles with these learned patterns. Synthetic data now samples from vendor distribution, producing multi-vendor training set without manual labeling.

---

## Insight 1: The 80/20 Curriculum is Optimal (Empirically)

### The Experiment

Tested multiple curriculum distributions:

| Curriculum | Nominal % | Edge-case % | Real PDF Accuracy |
|------------|-----------|-------------|-------------------|
| Uniform | 20% each level | 20% each level | 68% |
| Heavy-focused | 40% | 60% | 71% (over-fit to edge) |
| Clean-focused | 80% | 20% | 65% (under-fit to edge) |
| 80/20 optimal | 70% (L1-L3) | 30% (L4-L5) | 76% |
| Final | 70% (L1-L3) | 30% (L4-L5) | 78% |

### Why 80/20 Works

1. **Real-world distribution:** ~70-80% of financial PDFs are clean to moderately noisy. ~20-30% are edge cases.

2. **Learning dynamics:** Models need sufficient clean examples to learn structure, plus enough edge cases for robustness.

3. **Gradient signal:** Too many edge cases = noisy gradients. Too few = over-confident on nominal.

### Implementation

```yaml
degradation_distribution:
  1: 0.20  # Clean (20%)
  2: 0.25  # Mild (25%)
  3: 0.25  # Moderate (25%)
  4: 0.20  # Heavy (20%)
  5: 0.10  # Extreme (10%)

# Effective split: 70% nominal (L1-L3), 30% edge-case (L4-L5)
```

---

## Insight 2: Text-Native PDFs Eliminate OCR Noise

### The Problem

Many synthetic data approaches render PDFs as images, then apply image augmentation (blur, rotation, noise). This adds a variable we can't control: OCR error.

### The Solution

Generate text-native PDFs where text is encoded as vectors, not pixels. Benefits:

1. **Perfect text extraction:** No OCR errors from our generation
2. **Controlled noise:** All degradation is intentional and measurable
3. **Faster processing:** No OCR step during feature extraction
4. **Precise bbox alignment:** Coordinates match exactly between generation and extraction

### When Image-Based Matters

For scanned document use cases, would need separate OCR robustness training. Current system assumes text-native input (covers ~80% of enterprise financial documents).

---

## Insight 3: Reproducibility Enables Ablation Studies

### The Design Decision

All generation is deterministic given seed + config:

```python
def generate_corpus(seed=42, config='default.yml'):
    np.random.seed(seed)
    # Same seed + config = identical corpus
```

### Why This Matters

**Ablation studies:**
- Generate corpus with degradation level 3
- Generate identical corpus with degradation level 5
- Compare model performance → isolate effect of degradation

**Bug reproduction:**
- "Model fails on doc_id=ABC123"
- Re-generate that exact document
- Debug with known ground truth

**Experiment tracking:**
- Log seed + config with each experiment
- Fully reproducible results
- Can re-run experiments months later

### Implementation

Every document ID encodes its generation parameters:

```
BUILDIUM__00042__2025-01__L3_HORI_P
│         │      │       │  │    │
│         │      │       │  │    └── Orientation: Portrait
│         │      │       │  └─────── Layout: Horizontal Ledger
│         │      │       └────────── Degradation Level: 3
│         │      └────────────────── Period: Jan 2025
│         └───────────────────────── Index: 42
└─────────────────────────────────── Vendor: Buildium
```

---

## What We Would Do Differently

1. **Start with extraction parity from day one.** Wasted 2 weeks on "fast" generation that didn't transfer.

2. **Collect real PDFs earlier.** Even 20 real documents would have revealed the circular feature problem immediately.

3. **Build validation pipeline before generation pipeline.** Caught bugs faster once validation existed.

4. **Document vendor patterns as discovered.** Lost knowledge when adding new vendors because patterns weren't recorded.

5. **Version synthetic data.** Early experiments mixed data versions, making comparison difficult.
