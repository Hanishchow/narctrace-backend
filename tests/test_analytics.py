"""Unit tests for the deterministic analytics aggregation (PRD v2 Track C)."""
from app.analytics import compute_summary


def _rec(result, profile_id="SIM-PROFILE-ALPHA", operator="OP-1", ts="2026-09-10T10:00:00Z", passed=True):
    return {
        "result": result,
        "profile_id": profile_id,
        "operator_id": operator,
        "timestamp_utc": ts,
        "quality": {"passed": passed},
    }


def test_empty_summary():
    s = compute_summary([])
    assert s["success"] is True
    assert s["totals"]["total"] == 0
    assert s["rates"]["positive_rate"] == 0.0
    assert s["by_day"] == []


def test_totals_and_rates():
    records = [
        _rec("Positive"), _rec("Positive"), _rec("Negative"), _rec("Inconclusive"),
    ]
    s = compute_summary(records)
    assert s["totals"] == {
        "total": 4, "positive": 2, "negative": 1, "inconclusive": 1, "quality_rejected": 0,
    }
    assert s["rates"]["positive_rate"] == 0.5
    assert s["rates"]["negative_rate"] == 0.25
    assert s["rates"]["inconclusive_rate"] == 0.25


def test_quality_rejected_counted():
    records = [_rec("Positive", passed=True), _rec("Negative", passed=False)]
    s = compute_summary(records)
    assert s["totals"]["quality_rejected"] == 1


def test_by_profile_and_operator():
    records = [
        _rec("Positive", profile_id="SIM-PROFILE-ALPHA", operator="OP-1"),
        _rec("Negative", profile_id="SIM-PROFILE-BETA", operator="OP-1"),
        _rec("Positive", profile_id="SIM-PROFILE-ALPHA", operator="OP-2"),
    ]
    s = compute_summary(records)
    profiles = {p["profile_id"]: p["count"] for p in s["by_profile"]}
    assert profiles == {"SIM-PROFILE-ALPHA": 2, "SIM-PROFILE-BETA": 1}
    operators = {o["operator_id"]: o["count"] for o in s["by_operator"]}
    assert operators == {"OP-1": 2, "OP-2": 1}


def test_by_day_trend():
    records = [
        _rec("Positive", ts="2026-09-10T09:00:00Z"),
        _rec("Negative", ts="2026-09-10T18:00:00Z"),
        _rec("Positive", ts="2026-09-11T12:00:00Z"),
    ]
    s = compute_summary(records)
    assert s["by_day"] == [
        {"date": "2026-09-10", "count": 2, "positive": 1},
        {"date": "2026-09-11", "count": 1, "positive": 1},
    ]
