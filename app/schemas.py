"""
Pydantic request/response schemas for the public API contract (PRD §4).
"""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel


# --- Auth ---
class LoginRequest(BaseModel):
    badge_id: str
    password: str


class Officer(BaseModel):
    id: str
    name: str
    badge_id: str


class LoginResponse(BaseModel):
    token: str
    officer: Officer


# --- Health ---
class HealthResponse(BaseModel):
    status: str
    version: str


# --- Analyze result (PRD §4) ---
class QualityBlock(BaseModel):
    passed: bool
    blur_score: float
    exposure_status: str
    glare: bool


class ColorBlock(BaseModel):
    hex: str
    lab: List[float]
    delta_e_positive: float
    delta_e_negative: float


class ProfileBlock(BaseModel):
    profile_id: str
    name: str
    version: str


class GpsBlock(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    label: Optional[str] = None


class EvidenceBlock(BaseModel):
    timestamp_utc: str
    timestamp_local: str
    operator_id: str
    gps: Optional[GpsBlock] = None
    image_sha256: str
    image_url: str


class AnalysisResult(BaseModel):
    success: bool
    test_id: str
    result: str
    quality: QualityBlock
    color: ColorBlock
    profile: ProfileBlock
    evidence: EvidenceBlock
    disclaimer: str


# --- Profiles / history ---
class ProfilesResponse(BaseModel):
    success: bool
    profiles: List[Dict[str, Any]]


class HistoryListResponse(BaseModel):
    success: bool
    count: int
    records: List[Dict[str, Any]]


class HistoryRecordResponse(BaseModel):
    success: bool
    record: Optional[Dict[str, Any]] = None
