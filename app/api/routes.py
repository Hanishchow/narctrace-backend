"""
API routes under `/api` (PRD §4 contract).
"""
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.analytics import compute_summary
from app.config import get_settings
from app.constants import STANDARD_DISCLAIMER
from app.engine import list_available_profiles, get_kit_profile
from app.evidence import build_evidence_record, verify_image_integrity
from app.passport import canonical_manifest, custody_event_hash, verify_manifest
from app.pipeline import run_pipeline
from app.schemas import (
    AnalysisResult, HealthResponse, HistoryListResponse, HistoryRecordResponse,
    LoginRequest, LoginResponse, ProfilesResponse, CaseCreateRequest, CaseTransitionRequest, LabReportRequest,
)
from app.store import Store, StoreError
from app.api.deps import store_dep, require_actor, require_bearer

router = APIRouter(prefix="/api")


def _analysis_response_from_record(record: dict, store: Store) -> AnalysisResult:
    """Reconstructs a receipt response for an idempotent retry without reanalysis."""
    return AnalysisResult(
        success=True,
        test_id=record["test_id"],
        result=record["result"],
        quality=record["quality"],
        color=record["color"],
        profile=record["profile"],
        evidence={
            "timestamp_utc": record["timestamp_utc"],
            "timestamp_local": record["timestamp_local"],
            "operator_id": record["operator_id"],
            "gps": record.get("gps"),
            "image_sha256": record["image_sha256"],
            "image_url": store.evidence_image_url(record["image_path"]),
        },
        explanation={
            "method": "Reference-card calibrated CIELAB comparison",
            "summary": "This submission was already accepted; the original evidence receipt is shown.",
            "pipeline_version": "1.1.0-deterministic",
            "classification_rule": "Stored immutable analysis result.",
        },
        disclaimer=STANDARD_DISCLAIMER,
    )


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


@router.post("/capture-preview")
async def capture_preview(
    image: UploadFile = File(...),
    profile_id: str = Form(...),
    _actor: dict = Depends(require_actor),
) -> dict:
    """Runs non-persistent quality analysis to guide a recapture before submission."""
    profile = get_kit_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id '{profile_id}'.")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    if len(image_bytes) > get_settings().MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds upload limit.")
    result = run_pipeline(image_bytes, profile)
    quality = result.quality_report
    return {
        "success": result.success,
        "card_detected": result.card_detected,
        "guidance": (
            "Capture is ready for final analysis."
            if result.success
            else " · ".join(quality.issues) or "Retake with the full reference card visible."
        ),
        "quality": {
            "passed": quality.passed,
            "blur_score": quality.blur_score,
            "exposure_status": quality.exposure_status,
            "glare": quality.glare_detected,
            "issues": quality.issues,
        },
    }


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    image: UploadFile = File(...),
    profile_id: str = Form(...),
    operator_id: str = Form(default=""),
    gps: str = Form(default=""),
    case_id: str = Form(default=""),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> AnalysisResult:
    profile = get_kit_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id '{profile_id}'.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")
    if len(image_bytes) > get_settings().MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {get_settings().MAX_UPLOAD_BYTES // (1024 * 1024)} MiB upload limit.",
        )

    gps_data: Optional[dict] = None
    if gps and gps.strip():
        try:
            gps_data = json.loads(gps)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="`gps` must be valid JSON.")

    actor_id = str(actor.get("badge_id") or actor.get("id") or operator_id)
    payload_hash = hashlib.sha256(
        image_bytes
        + json.dumps({"profile_id": profile_id, "gps": gps_data, "actor_id": actor_id}, sort_keys=True).encode()
    ).hexdigest()

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
        if idempotency_key:
            receipt = store.claim_idempotency(idempotency_key, payload_hash, test_id)
            if not receipt["created"]:
                if receipt["payload_hash"] != payload_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was reused with a different capture payload.",
                    )
                existing = store.get_record(receipt["test_id"])
                if existing:
                    return _analysis_response_from_record(existing, store)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This capture is still being saved. Retry with the same idempotency key.",
                )
        image_path = store.save_evidence_image(test_id, image_bytes)
        record = build_evidence_record(
            test_id=test_id,
            image_bytes=image_bytes,
            result=result.result,
            profile=profile,
            quality=result.quality_report,
            color_metrics=result.color_metrics,
            image_path=image_path,
            # Client-supplied operator IDs are not authoritative. Preserve the
            # form field temporarily for legacy clients, but use verified identity.
            operator_id=actor_id,
            gps=gps_data,
        )
        store.save_record(record)
        if case_id.strip():
            store.link_evidence_to_case(case_id.strip(), record.test_id, str(actor["id"]))
        if idempotency_key:
            store.finalize_idempotency(idempotency_key)
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
        explanation={
            "method": "Reference-card calibrated CIELAB comparison",
            "summary": result.reasoning,
            "pipeline_version": "1.1.0-deterministic",
            "classification_rule": (
                "The calibrated reaction colour is compared with the selected profile's "
                "simulated positive and negative reference targets using CIEDE2000 distance."
            ),
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


@router.get("/analytics/summary")
def analytics_summary(
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> dict:
    """Presentation-ready aggregate stats over all evidence records (PRD v2 Track C)."""
    try:
        records = store.search_records(limit=1_000_000)
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"Analytics read error: {e}")
    return compute_summary(records)


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


@router.get("/history/{test_id}/verify")
def verify_evidence(
    test_id: str,
    _token: str = Depends(require_bearer),
    store: Store = Depends(store_dep),
) -> dict:
    """Checks currently stored evidence bytes against its recorded SHA-256 hash."""
    try:
        record = store.get_record(test_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"No record for test_id '{test_id}'.")
        found = store.read_evidence_bytes(record["image_path"])
    except StoreError as e:
        raise HTTPException(status_code=502, detail=f"Evidence verification failed: {e}")
    if found is None:
        return {"success": False, "test_id": test_id, "valid": False, "reason": "Evidence image is missing."}
    image_valid = verify_image_integrity(found[0], record["image_sha256"])
    stored_manifest = store.get_evidence_manifest(test_id)
    manifest_valid = bool(
        stored_manifest
        and canonical_manifest(record) == stored_manifest["manifest"]
        and verify_manifest(stored_manifest["manifest"], stored_manifest["signature"], get_settings().EVIDENCE_SIGNING_KEY)
    )
    valid = image_valid and manifest_valid
    return {
        "success": valid,
        "test_id": test_id,
        "valid": valid,
        "expected_sha256": record["image_sha256"],
        "image_valid": image_valid,
        "manifest_valid": manifest_valid,
        "reason": "Image bytes and signed evidence passport match the receipt." if valid else "Evidence image or signed passport does not match the receipt.",
    }


@router.post("/v2/cases")
def create_case(
    body: CaseCreateRequest,
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    try:
        return {"success": True, "case": store.create_case(body.reference, body.title, str(actor["id"]))}
    except StoreError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/v2/cases")
def list_cases(
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    try:
        return {"success": True, "cases": store.list_cases(str(actor["id"]))}
    except StoreError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/v2/cases/{case_id}")
def get_case(
    case_id: str,
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    try:
        case = store.get_case(case_id)
    except StoreError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not case or case["owner_id"] != str(actor["id"]):
        raise HTTPException(status_code=404, detail="Case was not found.")
    return {"success": True, "case": case}


@router.get("/v2/cases/{case_id}/verify")
def verify_case_timeline(
    case_id: str,
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    case = store.get_case(case_id)
    if not case or case["owner_id"] != str(actor["id"]):
        raise HTTPException(status_code=404, detail="Case was not found.")
    previous_hash = ""
    valid = True
    for event in case.get("events", []):
        expected = custody_event_hash(
            case_id, event["sequence"], event["action"], event["actor_id"], event["created_at"], previous_hash,
            get_settings().EVIDENCE_SIGNING_KEY,
        )
        if event.get("previous_hash") != previous_hash or event.get("event_hash") != expected:
            valid = False
            break
        previous_hash = event["event_hash"]
    return {"success": valid, "case_id": case_id, "valid": valid, "event_count": len(case.get("events", []))}


@router.post("/v2/cases/{case_id}/events")
def transition_case(
    case_id: str,
    body: CaseTransitionRequest,
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    try:
        return {
            "success": True,
            "case": store.transition_case(case_id, body.action, str(actor["id"]), body.expected_version),
        }
    except StoreError as e:
        message = str(e)
        status_code = status.HTTP_409_CONFLICT if "changed" in message else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=message)


@router.post("/v2/cases/{case_id}/lab-reports")
def add_lab_report(
    case_id: str,
    body: LabReportRequest,
    actor: dict = Depends(require_actor),
    store: Store = Depends(store_dep),
) -> dict:
    try:
        case = store.add_lab_report(
            case_id, body.laboratory, body.outcome, body.report_reference, str(actor["id"])
        )
        return {"success": True, "case": case}
    except StoreError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


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
