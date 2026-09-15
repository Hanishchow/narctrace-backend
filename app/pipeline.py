"""
Unified Analysis Pipeline (adapted from Technocrats reference `src/pipeline.py`).
Deterministic stages: decode -> reference-card detect + perspective normalize ->
quality gate -> white-patch illuminant calibration -> RGB->CIELAB (D65) -> CIEDE2000 ΔE ->
kit-profile rules -> result engine. Persistence/evidence assembly happens in the API layer.
"""
import cv2
import numpy as np
from typing import Dict, Any, Optional

from app.models import KitProfile, QualityReport, ColorMetrics
from app.quality import assess_image_quality
from app.detection import detect_prototype_card, DetectedCard
from app.calibration import apply_color_calibration
from app.color import compute_color_metrics
from app.engine import classify_result


class PipelineExecutionResult:
    def __init__(
        self,
        success: bool,
        quality_report: QualityReport,
        card_detected: bool,
        result: Optional[str] = None,
        reasoning: str = "",
        color_metrics: Optional[ColorMetrics] = None,
    ):
        self.success = success
        self.quality_report = quality_report
        self.card_detected = card_detected
        self.result = result
        self.reasoning = reasoning
        self.color_metrics = color_metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "quality_report": self.quality_report.to_dict(),
            "card_detected": self.card_detected,
            "result": self.result,
            "reasoning": self.reasoning,
            "color_metrics": self.color_metrics.to_dict() if self.color_metrics else None,
        }


def run_pipeline(image_bytes: bytes, profile: KitProfile) -> PipelineExecutionResult:
    """Executes the deterministic analysis pipeline (no persistence, no disk writes)."""
    # 1. Decode
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None:
        quality = QualityReport(
            passed=False, blur_score=0.0, blur_passed=False,
            exposure_status="invalid", exposure_passed=False,
            glare_detected=False, glare_passed=False, card_visible=False,
            issues=["Failed to decode image. Unsupported or corrupted format."],
        )
        return PipelineExecutionResult(
            success=False, quality_report=quality, card_detected=False,
            reasoning="Image decoding failed.",
        )

    # 2. Reference card detection
    card: DetectedCard = detect_prototype_card(img_bgr)

    # 3. Quality gate
    quality = assess_image_quality(
        img_bgr,
        card_detected=card.found,
        reaction_mask=card.reaction_mask if card.found else None,
        warped_card=card.warped_card if card.found else None,
    )
    if not quality.passed:
        return PipelineExecutionResult(
            success=False, quality_report=quality, card_detected=card.found,
            reasoning=f"Image rejected due to quality check failures: {'; '.join(quality.issues)}",
        )

    # 4. Calibration (linear white-patch scaling)
    white_rgb = card.patches_rgb.get("white", (240.0, 240.0, 240.0))
    raw_reaction_rgb = card.reaction_rgb if card.reaction_rgb is not None else (128, 128, 128)
    calibrated_rgb, _cal = apply_color_calibration(
        observed_reaction_rgb=raw_reaction_rgb, observed_white_rgb=white_rgb
    )

    # 5. CIELAB + CIEDE2000
    color_metrics = compute_color_metrics(
        raw_rgb=(int(raw_reaction_rgb[0]), int(raw_reaction_rgb[1]), int(raw_reaction_rgb[2])),
        calibrated_rgb=calibrated_rgb,
        target_pos_lab=profile.positive_target.target_lab,
        target_neg_lab=profile.negative_target.target_lab,
    )

    # 6. Classification
    outcome, reasoning = classify_result(color_metrics, profile)

    return PipelineExecutionResult(
        success=True, quality_report=quality, card_detected=True,
        result=outcome, reasoning=reasoning, color_metrics=color_metrics,
    )
