"""Layout degradation engine for generating varied table appearances."""

from dataclasses import dataclass
from typing import Tuple
import numpy as np


@dataclass
class DegradationParams:
    """Parameters for a degradation level."""
    level: int
    name: str
    # Position jitter (in points)
    position_jitter: float
    # Font size variation (multiplier range, e.g., 0.95-1.05)
    font_size_min: float
    font_size_max: float
    # Grid line probability (1.0 = all lines, 0.0 = no lines)
    grid_line_prob: float
    # Row height variation (multiplier range)
    row_height_min: float
    row_height_max: float
    # Cell padding variation (multiplier range)
    padding_min: float
    padding_max: float
    # Column width variation (how much columns can vary from template)
    col_width_variation: float
    # Alignment jitter (probability of wrong alignment)
    align_jitter_prob: float
    # Character spacing variation (multiplier)
    char_spacing_variation: float


# Define 5 degradation levels
DEGRADATION_LEVELS = {
    1: DegradationParams(
        level=1,
        name="Clean",
        position_jitter=0.0,
        font_size_min=1.0,
        font_size_max=1.0,
        grid_line_prob=1.0,
        row_height_min=1.0,
        row_height_max=1.0,
        padding_min=1.0,
        padding_max=1.0,
        col_width_variation=0.0,
        align_jitter_prob=0.0,
        char_spacing_variation=0.0,
    ),
    2: DegradationParams(
        level=2,
        name="Mild",
        position_jitter=1.0,
        font_size_min=0.95,
        font_size_max=1.05,
        grid_line_prob=0.95,
        row_height_min=0.95,
        row_height_max=1.05,
        padding_min=0.9,
        padding_max=1.1,
        col_width_variation=0.03,
        align_jitter_prob=0.02,
        char_spacing_variation=0.01,
    ),
    3: DegradationParams(
        level=3,
        name="Moderate",
        position_jitter=2.0,
        font_size_min=0.90,
        font_size_max=1.10,
        grid_line_prob=0.85,
        row_height_min=0.90,
        row_height_max=1.10,
        padding_min=0.8,
        padding_max=1.2,
        col_width_variation=0.08,
        align_jitter_prob=0.05,
        char_spacing_variation=0.02,
    ),
    4: DegradationParams(
        level=4,
        name="Heavy",
        position_jitter=3.5,
        font_size_min=0.85,
        font_size_max=1.15,
        grid_line_prob=0.70,
        row_height_min=0.85,
        row_height_max=1.20,
        padding_min=0.6,
        padding_max=1.4,
        col_width_variation=0.12,
        align_jitter_prob=0.10,
        char_spacing_variation=0.03,
    ),
    5: DegradationParams(
        level=5,
        name="Extreme",
        position_jitter=5.0,
        font_size_min=0.80,
        font_size_max=1.25,
        grid_line_prob=0.50,
        row_height_min=0.75,
        row_height_max=1.30,
        padding_min=0.4,
        padding_max=1.6,
        col_width_variation=0.18,
        align_jitter_prob=0.15,
        char_spacing_variation=0.05,
    ),
}


class DegradationEngine:
    """Apply degradation effects to table rendering."""

    def __init__(self, level: int, rng: np.random.Generator):
        """Initialize with degradation level (1-5) and RNG."""
        self.level = max(1, min(5, level))
        self.params = DEGRADATION_LEVELS[self.level]
        self.rng = rng

    def apply_position_jitter(self, x: float, y: float) -> Tuple[float, float]:
        """Apply random position jitter to coordinates."""
        if self.params.position_jitter == 0:
            return x, y
        jitter_x = self.rng.uniform(-self.params.position_jitter, self.params.position_jitter)
        jitter_y = self.rng.uniform(-self.params.position_jitter, self.params.position_jitter)
        return x + jitter_x, y + jitter_y

    def apply_font_size_variation(self, base_size: int) -> int:
        """Apply font size variation."""
        multiplier = self.rng.uniform(self.params.font_size_min, self.params.font_size_max)
        return max(6, int(base_size * multiplier))

    def should_draw_grid_line(self) -> bool:
        """Determine if a grid line should be drawn."""
        return self.rng.random() < self.params.grid_line_prob

    def apply_row_height_variation(self, base_height: float) -> float:
        """Apply row height variation."""
        multiplier = self.rng.uniform(self.params.row_height_min, self.params.row_height_max)
        return base_height * multiplier

    def apply_padding_variation(self, base_padding: float) -> float:
        """Apply cell padding variation."""
        multiplier = self.rng.uniform(self.params.padding_min, self.params.padding_max)
        return max(1.0, base_padding * multiplier)

    def apply_column_width_variation(self, base_width: float) -> float:
        """Apply column width variation."""
        if self.params.col_width_variation == 0:
            return base_width
        variation = self.rng.uniform(-self.params.col_width_variation, self.params.col_width_variation)
        return base_width * (1 + variation)

    def should_misalign(self) -> bool:
        """Determine if alignment should be wrong."""
        return self.rng.random() < self.params.align_jitter_prob

    def get_misaligned_alignment(self, original: str) -> str:
        """Get a different alignment than the original."""
        alignments = ["left", "center", "right"]
        alignments.remove(original)
        return self.rng.choice(alignments)

    def apply_char_spacing(self, text: str) -> str:
        """Apply character spacing variation (simulated by adding spaces)."""
        if self.params.char_spacing_variation == 0 or len(text) < 3:
            return text
        # Occasionally add extra spaces between chars
        if self.rng.random() < self.params.char_spacing_variation * 5:
            # Insert an extra space at a random position
            pos = self.rng.integers(1, len(text))
            return text[:pos] + " " + text[pos:]
        return text


def get_degradation_engine(level: int, rng: np.random.Generator) -> DegradationEngine:
    """Get a degradation engine for the specified level."""
    return DegradationEngine(level, rng)
