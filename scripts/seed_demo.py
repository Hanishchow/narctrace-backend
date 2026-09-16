"""
Seed ~40 realistic evidence records across the last 14 days, both kit profiles, and
all three results — so the /api/analytics/summary dashboard looks populated for a demo.

Usage (from the backend repo root, venv active):
    python scripts/seed_demo.py            # seeds into the local SQLite store
    python scripts/seed_demo.py --count 60

Records go through the LocalStore (STORE_BACKEND=local), same store the API reads.
All values are SIMULATED/PROXY demonstration data.
"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as a bare script: ensure the repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STORE_BACKEND", "local")

from app.models import EvidenceRecord  # noqa: E402
from app.store import get_store  # noqa: E402

PROFILES = {
    "SIM-PROFILE-ALPHA": {"name": "Simulated Reagent Alpha (Purple Proxy Assay)", "version": "1.0-simulated"},
    "SIM-PROFILE-BETA": {"name": "Simulated Reagent Beta (Cobalt Blue Proxy Assay)", "version": "1.0-simulated"},
}
RESULTS = ["Positive", "Negative", "Inconclusive"]
RESULT_WEIGHTS = [0.45, 0.4, 0.15]  # plausible field distribution
OPERATORS = ["FIELD-OP-01", "FIELD-OP-02", "FIELD-OP-07", "SUP-COMMAND-01"]
HEX_BY_RESULT = {"Positive": "#5b2d91", "Negative": "#c9a24b", "Inconclusive": "#7c6f86"}


def make_record(store, when: datetime) -> EvidenceRecord:
    result = random.choices(RESULTS, weights=RESULT_WEIGHTS, k=1)[0]
    profile_id = random.choice(list(PROFILES))
    test_id = store.next_test_id()
    fake_bytes = f"{test_id}:{when.isoformat()}:{random.random()}".encode()
    sha = hashlib.sha256(fake_bytes).hexdigest()
    passed = random.random() > 0.06  # a few quality-flagged records
    return EvidenceRecord(
        test_id=test_id,
        operator_id=random.choice(OPERATORS),
        result=result,
        profile_id=profile_id,
        profile={"profile_id": profile_id, **PROFILES[profile_id]},
        timestamp_utc=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        timestamp_local=when.strftime("%Y-%m-%d %H:%M:%S"),
        gps={"lat": round(12.9 + random.uniform(-0.2, 0.2), 5),
             "lon": round(77.6 + random.uniform(-0.2, 0.2), 5),
             "label": random.choice(["Bengaluru, KA", "Mysuru, KA", "Hubli, KA"])},
        color={"hex": HEX_BY_RESULT[result], "lab": [56.4, 16.2, -8.3],
               "delta_e_positive": round(random.uniform(2, 40), 2),
               "delta_e_negative": round(random.uniform(2, 40), 2)},
        quality={"passed": passed, "blur_score": round(random.uniform(80, 1600), 1),
                 "exposure_status": "normal", "glare": not passed},
        image_sha256=sha,
        image_path=f"{test_id}.jpg",
        created_at=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    store = get_store()
    now = datetime.now(timezone.utc)

    made = 0
    for _ in range(args.count):
        day_offset = random.randint(0, args.days - 1)
        when = now - timedelta(days=day_offset, hours=random.randint(0, 23), minutes=random.randint(0, 59))
        store.save_record(make_record(store, when))
        made += 1

    print(f"Seeded {made} demo evidence records over the last {args.days} days into the local store.")
    print("Start the server and open /api/analytics/summary (with a Bearer token) to see them.")


if __name__ == "__main__":
    main()
