"""Regenerate the synthetic demo/proxy samples under data/demo_samples/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.demo_data import generate_all_demo_samples  # noqa: E402

if __name__ == "__main__":
    generate_all_demo_samples(overwrite="--overwrite" in sys.argv)
    print("Demo samples generated under data/demo_samples/.")
