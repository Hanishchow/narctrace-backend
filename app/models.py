"""
Domain dataclasses (ported from the Technocrats reference `src/models.py`) plus the
InsForge-aligned EvidenceRecord (PRD §6). Pydantic response schemas live in schemas.py.
All values are SIMULATED / PROXY.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class KitTarget:
    label: str
    target_lab: List[float]  # [L*, a*, b*]
    max_delta_e: float


@dataclass
class KitProfile:
    profile_id: str
    name: str
    version: str
    is_simulated: bool
    disclaimer: str
    reaction_type: str
    timing_seconds: int
    positive_target: KitTarget
    negative_target: KitTarget
    ambiguity_margin: float = 4.0
    max_acceptable_delta_e: float = 25.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KitProfile":
        pos_data = data["targets"]["positive"]
        neg_data = data["targets"]["negative"]
        inconc = data.get("inconclusive_threshold", {})
        return cls(
            profile_id=data["profile_id"],
            name=data["name"],
            version=data.get("version", "1.0-simulated"),
            is_simulated=data.get("is_simulated", True),
            disclaimer=data.get("disclaimer", "SIMULATED / PROXY FIELD-TEST KIT ONLY."),
            reaction_type=data.get("reaction_type", "colorimetric_proxy"),
            timing_seconds=data.get("timing_seconds", 30),
            positive_target=KitTarget(
                label=pos_data.get("label", "Positive Target"),
                target_lab=[float(x) for x in pos_data["target_lab"]],
                max_delta_e=float(pos_data.get("max_delta_e", 14.0)),
            ),
            negative_target=KitTarget(
                label=neg_data.get("label", "Negative Target"),
                target_lab=[float(x) for x in neg_data["target_lab"]],
                max_delta_e=float(neg_data.get("max_delta_e", 12.0)),
            ),
            ambiguity_margin=float(inconc.get("ambiguity_margin", 4.0)),
            max_acceptable_delta_e=float(inconc.get("max_acceptable_delta_e", 25.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "version": self.version,
            "is_simulated": self.is_simulated,
            "disclaimer": self.disclaimer,
            "reaction_type": self.reaction_type,
            "timing_seconds": self.timing_seconds,
            "targets": {
                "positive": asdict(self.positive_target),
                "negative": asdict(self.negative_target),
            },
            "inconclusive_threshold": {
                "ambiguity_margin": self.ambiguity_margin,
                "max_acceptable_delta_e": self.max_acceptable_delta_e,
            },
        }


@dataclass
class QualityReport:
    passed: bool
    blur_score: float
    blur_passed: bool
    exposure_status: str  # "normal", "underexposed", "overexposed"
    exposure_passed: bool
    glare_detected: bool
    glare_passed: bool
    card_visible: bool
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationResult:
    observed_white_rgb: List[float]
    gains: List[float]  # [k_r, k_g, k_b]
    success: bool
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ColorMetrics:
    raw_rgb: List[int]
    calibrated_rgb: List[int]
    calibrated_lab: List[float]
    delta_e_positive: float
    delta_e_negative: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_rgb": self.raw_rgb,
            "calibrated_rgb": self.calibrated_rgb,
            "calibrated_lab": [round(x, 2) for x in self.calibrated_lab],
            "delta_e_positive": round(self.delta_e_positive, 2),
            "delta_e_negative": round(self.delta_e_negative, 2),
        }


@dataclass
class EvidenceRecord:
    """InsForge `evidence_records`-aligned record (PRD §6)."""
    test_id: str
    operator_id: str
    result: str  # "Positive" | "Negative" | "Inconclusive"
    profile_id: str
    profile: Dict[str, Any]      # {profile_id, name, version}
    timestamp_utc: str
    timestamp_local: str
    gps: Optional[Dict[str, Any]]  # {lat, lon, label} or None
    color: Dict[str, Any]          # {hex, lab, delta_e_positive, delta_e_negative}
    quality: Dict[str, Any]        # {passed, blur_score, exposure_status, glare}
    image_sha256: str
    image_path: str                # storage key in `evidence` bucket
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
