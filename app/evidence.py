"""
Digital Evidence & Integrity (adapted from Technocrats reference `src/evidence.py`).
SHA-256 over raw image bytes; Test ID format `FT-#####` (PRD §4). Persistence is delegated
to the Store layer — this module only computes hashes/ids and assembles the domain record.
"""
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.color import rgb_to_hex
from app.models import EvidenceRecord, KitProfile, QualityReport, ColorMetrics


def compute_image_sha256(image_bytes: bytes) -> str:
    """SHA-256 of raw image bytes (tamper-evidence integrity hash)."""
    return hashlib.sha256(image_bytes).hexdigest()


def verify_image_integrity(image_bytes: bytes, expected_hash: str) -> bool:
    return compute_image_sha256(image_bytes).lower() == expected_hash.lower()


def format_test_id(sequence: int) -> str:
    """Formats a monotonic sequence number as `FT-#####` (zero-padded to 5 digits)."""
    return f"FT-{sequence:05d}"


def _normalize_gps(gps: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalizes incoming GPS to {lat, lon, label} or None. Accepts lat/latitude, lon/longitude."""
    if not gps:
        return None
    lat = gps.get("lat", gps.get("latitude"))
    lon = gps.get("lon", gps.get("longitude"))
    label = gps.get("label") or gps.get("note")
    if lat is None or lon is None:
        return None
    return {
        "lat": float(lat),
        "lon": float(lon),
        "label": label,
    }


def build_evidence_record(
    test_id: str,
    image_bytes: bytes,
    result: str,
    profile: KitProfile,
    quality: QualityReport,
    color_metrics: ColorMetrics,
    image_path: str,
    operator_id: Optional[str] = None,
    gps: Optional[Dict[str, Any]] = None,
) -> EvidenceRecord:
    """Assembles the InsForge-aligned evidence record (PRD §6)."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    image_hash = compute_image_sha256(image_bytes)
    operator = (operator_id or "").strip() or "FIELD-OP-DEFAULT"

    cal_rgb = color_metrics.calibrated_rgb
    color_block = {
        "hex": rgb_to_hex((cal_rgb[0], cal_rgb[1], cal_rgb[2])),
        "lab": [round(x, 2) for x in color_metrics.calibrated_lab],
        "delta_e_positive": round(color_metrics.delta_e_positive, 2),
        "delta_e_negative": round(color_metrics.delta_e_negative, 2),
    }
    quality_block = {
        "passed": quality.passed,
        "blur_score": quality.blur_score,
        "exposure_status": quality.exposure_status,
        "glare": quality.glare_detected,
    }

    return EvidenceRecord(
        test_id=test_id,
        operator_id=operator,
        result=result,
        profile_id=profile.profile_id,
        profile={
            "profile_id": profile.profile_id,
            "name": profile.name,
            "version": profile.version,
        },
        timestamp_utc=now_utc,
        timestamp_local=now_local,
        gps=_normalize_gps(gps),
        color=color_block,
        quality=quality_block,
        image_sha256=image_hash,
        image_path=image_path,
        created_at=now_utc,
    )
