"""Canonical evidence passport manifests for the local demonstration store."""
import hashlib
import hmac
import json
from typing import Any, Dict


def canonical_manifest(record: Dict[str, Any]) -> str:
    """Stable subset of immutable facts that define an evidence receipt."""
    values = {
        "test_id": record["test_id"],
        "operator_id": record["operator_id"],
        "result": record["result"],
        "profile_id": record["profile_id"],
        "timestamp_utc": record["timestamp_utc"],
        "image_sha256": record["image_sha256"],
        "color": record["color"],
        "quality": record["quality"],
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sign_manifest(manifest: str, signing_key: str) -> str:
    return hmac.new(signing_key.encode(), manifest.encode(), hashlib.sha256).hexdigest()


def verify_manifest(manifest: str, signature: str, signing_key: str) -> bool:
    return hmac.compare_digest(sign_manifest(manifest, signing_key), signature)


def custody_event_hash(
    case_id: str, sequence: int, action: str, actor_id: str, created_at: str, previous_hash: str, signing_key: str
) -> str:
    event = json.dumps(
        {"case_id": case_id, "sequence": sequence, "action": action, "actor_id": actor_id, "created_at": created_at, "previous_hash": previous_hash},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return sign_manifest(event, signing_key)
