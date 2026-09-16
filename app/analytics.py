"""
Deterministic analytics over persisted evidence records (PRD v2 Track C).

`compute_summary` is a pure function of a list of record dicts (as returned by
Store.search_records / get_record) so it is trivially unit-testable and store-agnostic.
No ML, no inference — plain aggregation for the command/presentation dashboard.
"""
from collections import Counter, defaultdict
from typing import Any, Dict, List


def _rate(n: int, d: int, ndigits: int = 3) -> float:
    return round(n / d, ndigits) if d else 0.0


def _result_of(record: Dict[str, Any]) -> str:
    return str(record.get("result") or "").strip().capitalize()


def compute_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate evidence records into presentation-ready statistics."""
    total = len(records)
    results = Counter(_result_of(r) for r in records)
    positive = results.get("Positive", 0)
    negative = results.get("Negative", 0)
    inconclusive = results.get("Inconclusive", 0)
    quality_rejected = sum(
        1 for r in records if not (r.get("quality") or {}).get("passed", True)
    )

    by_profile = Counter(r.get("profile_id") or "unknown" for r in records)
    by_operator = Counter(r.get("operator_id") or "unknown" for r in records)

    day_total: Dict[str, int] = defaultdict(int)
    day_positive: Dict[str, int] = defaultdict(int)
    for r in records:
        day = str(r.get("timestamp_utc") or "")[:10]
        if not day:
            continue
        day_total[day] += 1
        if _result_of(r) == "Positive":
            day_positive[day] += 1
    by_day = [
        {"date": d, "count": day_total[d], "positive": day_positive[d]}
        for d in sorted(day_total)
    ]

    return {
        "success": True,
        "totals": {
            "total": total,
            "positive": positive,
            "negative": negative,
            "inconclusive": inconclusive,
            "quality_rejected": quality_rejected,
        },
        "rates": {
            "positive_rate": _rate(positive, total),
            "negative_rate": _rate(negative, total),
            "inconclusive_rate": _rate(inconclusive, total),
        },
        "by_profile": [{"profile_id": k, "count": v} for k, v in by_profile.most_common()],
        "by_day": by_day,
        "by_operator": [{"operator_id": k, "count": v} for k, v in by_operator.most_common()],
    }
