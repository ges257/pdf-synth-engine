"""Configuration dataclasses and YAML loading for the generator."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml


@dataclass
class GeneratorConfig:
    """Main configuration for the synthetic data generator."""

    num_pdfs: int = 100
    seed: int = 42
    period_start: date = field(default_factory=lambda: date(2025, 1, 1))
    period_end: date = field(default_factory=lambda: date(2025, 12, 31))
    out_dir: Path = field(default_factory=lambda: Path("out"))

    # Table type mix: {type: (min_proportion, max_proportion)}
    table_mix: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "CASH_OUT": (0.15, 0.20),
        "CASH_IN": (0.15, 0.20),
        "BUDGET": (0.20, 0.25),
        "UNPAID": (0.10, 0.15),
        "AGING": (0.10, 0.15),
        "GL": (0.15, 0.20),
    })

    # Vendor distribution: {vendor: proportion}
    vendor_distribution: Dict[str, float] = field(default_factory=lambda: {
        "AKAM_OLD": 0.10,
        "AKAM_NEW": 0.10,
        "DOUGLAS": 0.10,
        "FIRSTSERVICE": 0.10,
        "LINDENWOOD": 0.10,
        "YARDI": 0.10,
        "APPFOLIO": 0.10,
        "BUILDIUM": 0.10,
        "MDS": 0.05,
        "CINC": 0.05,
        "OTHER": 0.10,
    })

    # Property type distribution (CIRA = Common Interest Realty Associations)
    # Valid CIRA types: Condos, HOAs, Co-ops, PUDs, Timeshares - NOT rentals
    property_type_distribution: Dict[str, float] = field(default_factory=lambda: {
        "CONDO": 0.50,       # Condominium associations
        "HOA": 0.30,         # Homeowners associations
        "COOP": 0.10,        # Cooperative housing
        "MIXED_USE": 0.10,   # Mixed-use (retail + residential condos)
    })

    # GL mask distribution
    gl_mask_distribution: Dict[str, float] = field(default_factory=lambda: {
        "NNNN": 0.30,
        "NNNNN": 0.30,
        "NN-NNNN-NN": 0.30,
        "NNNNNN": 0.10,
    })

    # Degradation level distribution (1=clean, 5=heavily degraded)
    degradation_distribution: Dict[int, float] = field(default_factory=lambda: {
        1: 0.20,
        2: 0.25,
        3: 0.25,
        4: 0.20,
        5: 0.10,
    })

    # Layout type distribution (per Appendix C)
    layout_distribution: Dict[str, float] = field(default_factory=lambda: {
        "horizontal_ledger": 0.55,
        "split_ledger": 0.10,
        "vertical_key_value": 0.10,
        "matrix_budget": 0.15,
        "ragged_pseudotable": 0.10,
    })

    # Page orientation distribution
    orientation_distribution: Dict[str, float] = field(default_factory=lambda: {
        "portrait": 0.60,
        "landscape": 0.40,
    })

    @classmethod
    def from_yaml(cls, path: Path) -> "GeneratorConfig":
        """Load configuration from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        # Convert date strings to date objects
        if "period_start" in data and isinstance(data["period_start"], str):
            data["period_start"] = date.fromisoformat(data["period_start"])
        if "period_end" in data and isinstance(data["period_end"], str):
            data["period_end"] = date.fromisoformat(data["period_end"])

        # Convert out_dir to Path
        if "out_dir" in data:
            data["out_dir"] = Path(data["out_dir"])

        # Convert degradation_distribution keys to int
        if "degradation_distribution" in data:
            data["degradation_distribution"] = {
                int(k): v for k, v in data["degradation_distribution"].items()
            }

        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to a YAML file."""
        data = {
            "num_pdfs": self.num_pdfs,
            "seed": self.seed,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "out_dir": str(self.out_dir),
            "table_mix": self.table_mix,
            "vendor_distribution": self.vendor_distribution,
            "property_type_distribution": self.property_type_distribution,
            "gl_mask_distribution": self.gl_mask_distribution,
            "degradation_distribution": self.degradation_distribution,
            "layout_distribution": self.layout_distribution,
            "orientation_distribution": self.orientation_distribution,
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_config(path: Optional[Path] = None) -> GeneratorConfig:
    """Load config from path or return default config."""
    if path is None:
        return GeneratorConfig()
    return GeneratorConfig.from_yaml(path)
