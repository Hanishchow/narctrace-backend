"""
API routes under `/api` (PRD §4 contract).
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.config import get_settings
from app.constants import STANDARD_DISCLAIMER
from app.engine import list_available_profiles, get_kit_profile
from app.evidence import build_evidence_record
from app.pipeline import run_pipeline
from app.schemas import (
    AnalysisResult, HealthResponse, HistoryListResponse, HistoryRecordResponse,
    LoginRequest, LoginResponse, ProfilesResponse,
)
from app.store import Store, StoreError
from app.api.deps import store_dep, require_bearer

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=get_settings().APP_VERSION)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, store: Store = Depends(store_dep)) -> LoginResponse:
    try:
        auth = store.authenticate(body.badge_id, body.password)
    except StoreError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return LoginResponse(token=auth.token, officer=auth.officer)


@router.get("/profiles", response_model=ProfilesResponse)
def profiles() -> ProfilesResponse:
    return ProfilesResponse(success=True, profiles=[p.to_dict() for p in list_available_profiles()])


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    image: UploadFile = File(...),
    profile_id: str = Form(...),
    operator_id: str = Form(default=""),
    gps: str = Form(default=""),
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> AnalysisResult:
    profile = get_kit_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id '{profile_id}'.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")

    gps_data: Optional[dict] = None
    if gps and gps.strip():
        try:
            gps_data = json.loads(gps)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="`gps` must be valid JSON.")

    result = run_pipeline(image_bytes, profile)

    # Quality gate failure -> 422 with recapture guidance (Inconclusive is a *success* result).
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success": False,
                "reason": result.reasoning,
                "quality": {
                    "passed": result.quality_report.passed,
                    "blur_score": result.quality_report.blur_score,
                    "exposure_status": result.quality_report.exposure_status,
                    "glare": result.quality_report.glare_detected,
                },
                "issues": result.quality_report.issues,
                "disclaimer": STANDARD_DISCLAIMER,
            },
        )

    try:
        test_id = store.next_test_id()
        image_path = store.save_evidence_image(test_id, image_bytes)
        record = build_evidence_record(
            test_id=test_id,
            image_bytes=image_bytes,
            result=result.result,
            profile=profile,
            quality=result.quality_report,
            color_metrics=result.color_metrics,
            image_path=image_path,
            operator_id=operator_id,
            gps=gps_data,
        )
        store.save_record(record)
        image_url = store.evidence_image_url(image_path)
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"Persistence error: {e}")

    return AnalysisResult(
        success=True,
        test_id=record.test_id,
        result=record.result,
        quality={
            "passed": result.quality_report.passed,
            "blur_score": result.quality_report.blur_score,
            "exposure_status": result.quality_report.exposure_status,
            "glare": result.quality_report.glare_detected,
        },
        color=record.color,
        profile=record.profile,
        evidence={
            "timestamp_utc": record.timestamp_utc,
            "timestamp_local": record.timestamp_local,
            "operator_id": record.operator_id,
            "gps": record.gps,
            "image_sha256": record.image_sha256,
            "image_url": image_url,
        },
        disclaimer=STANDARD_DISCLAIMER,
    )


@router.get("/history", response_model=HistoryListResponse)
def history(
    query: str = "",
    result: str = "",
    profile: str = "",
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> HistoryListResponse:
    try:
        records = store.search_records(
            query=query or None, result_filter=result or None, profile_filter=profile or None
        )
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"History read error: {e}")
    return HistoryListResponse(success=True, count=len(records), records=records)


@router.get("/history/{test_id}", response_model=HistoryRecordResponse)
def history_by_id(
    test_id: str,
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> HistoryRecordResponse:
    try:
        record = store.get_record(test_id)
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"History read error: {e}")
    if record is None:
        raise HTTPException(status_code=404, detail=f"No record for test_id '{test_id}'.")
    return HistoryRecordResponse(success=True, record=record)


@router.get("/evidence/{filename}")
def evidence(
    filename: str,
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> Response:
    try:
        found = store.read_evidence_bytes(filename)
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"Evidence read error: {e}")
    if found is None:
        raise HTTPException(status_code=404, detail=f"Evidence '{filename}' not found.")
    data, content_type = found
    return Response(content=data, media_type=content_type)
