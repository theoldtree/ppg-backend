"""
Build demographic baseline data for heart rate percentile comparison.

Data sources:
  - BUT-PPG 2.0.0 (Brno University): real HR measurements from 830 quality recordings
    subject-info.csv + quality-hr-ann.csv
  - Takazawa (1998): APG b/a reference values (kept — 30 Hz PPG insufficient to compute)
  - Ostchega et al. (2011) NHANES: fallback for groups with < MIN_SAMPLES subjects

Run:
    cd /path/to/ppg-backend
    source venv/bin/activate
    python scripts/build_demographic_baselines.py [--butppg-dir PATH]

Default BUT-PPG path: ~/Desktop/butppg-dataset/brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0/
"""
from __future__ import annotations

import argparse
import os
import sys
import statistics
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal, engine, Base
from app.db.models.measurement import DemographicBaseline

# ── Takazawa 1998 b/a reference (cannot be computed from 30 Hz data) ──────────
# Keyed by (gender, age_group) where age_group = floor(age / 10) * 10
TAKAZAWA_B_OVER_A = {
    # all genders
    ("all",    20): (-0.29, 0.13),
    ("all",    30): (-0.33, 0.14),
    ("all",    40): (-0.40, 0.15),
    ("all",    50): (-0.47, 0.16),
    ("all",    60): (-0.53, 0.18),
    # male
    ("male",   20): (-0.27, 0.12),
    ("male",   30): (-0.31, 0.13),
    ("male",   40): (-0.38, 0.15),
    ("male",   50): (-0.45, 0.16),
    ("male",   60): (-0.52, 0.17),
    # female
    ("female", 20): (-0.31, 0.13),
    ("female", 30): (-0.35, 0.14),
    ("female", 40): (-0.42, 0.15),
    ("female", 50): (-0.49, 0.16),
    ("female", 60): (-0.55, 0.18),
}

# ── NHANES fallback (Ostchega 2011) for groups without enough BUT-PPG data ───
NHANES_FALLBACK = {
    ("all",    20): (70.0, 11.5, 312, "Ostchega 2011 / NHANES"),
    ("all",    30): (71.5, 11.2, 489, "Ostchega 2011 / NHANES"),
    ("all",    40): (72.0, 11.8, 521, "Ostchega 2011 / NHANES"),
    ("all",    50): (72.5, 12.1, 504, "Ostchega 2011 / NHANES"),
    ("all",    60): (71.0, 12.5, 436, "Ostchega 2011 / NHANES"),
    ("male",   20): (68.5, 11.0, 158, "Ostchega 2011 / NHANES"),
    ("male",   30): (69.5, 10.8, 241, "Ostchega 2011 / NHANES"),
    ("male",   40): (70.0, 11.5, 264, "Ostchega 2011 / NHANES"),
    ("male",   50): (70.5, 11.9, 255, "Ostchega 2011 / NHANES"),
    ("male",   60): (69.5, 12.2, 221, "Ostchega 2011 / NHANES"),
    ("female", 20): (72.0, 11.8, 154, "Ostchega 2011 / NHANES"),
    ("female", 30): (73.5, 11.6, 248, "Ostchega 2011 / NHANES"),
    ("female", 40): (74.0, 12.2, 257, "Ostchega 2011 / NHANES"),
    ("female", 50): (74.5, 12.4, 249, "Ostchega 2011 / NHANES"),
    ("female", 60): (72.5, 12.8, 215, "Ostchega 2011 / NHANES"),
}

MIN_SAMPLES = 5  # Minimum subjects per group to use BUT-PPG data


def _age_group(age: float) -> Optional[int]:
    """Map age to decade bucket (20-69 only). Returns None for out-of-range."""
    g = int(age // 10) * 10
    return g if 20 <= g <= 60 else None


def load_butppg(butppg_dir: Path) -> dict[tuple[str, int], list[float]]:
    """
    Parse subject-info.csv and quality-hr-ann.csv from BUT-PPG dataset.
    Returns {(gender, age_group): [hr_values, ...]} for Quality=1 subjects.
    """
    subject_file = butppg_dir / "subject-info.csv"
    quality_file = butppg_dir / "quality-hr-ann.csv"

    if not subject_file.exists():
        raise FileNotFoundError(f"subject-info.csv not found at {subject_file}")
    if not quality_file.exists():
        raise FileNotFoundError(f"quality-hr-ann.csv not found at {quality_file}")

    # Parse subject-info.csv
    subjects: dict[str, dict] = {}
    with open(subject_file, encoding="utf-8-sig") as f:
        header = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if header is None:
                header = [h.lower().replace(" ", "_").replace("[", "").replace("]", "") for h in parts]
                continue
            row = dict(zip(header, parts))
            sid = row.get("id", "").strip()
            if sid:
                subjects[sid] = row

    # Parse quality-hr-ann.csv
    hr_data: dict[tuple[str, int], list[float]] = {}
    with open(quality_file, encoding="utf-8-sig") as f:
        header = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if header is None:
                header = [h.lower().strip() for h in parts]
                continue
            row = dict(zip(header, parts))

            # Only use Quality=1 recordings
            try:
                quality = int(row.get("quality", 0))
            except ValueError:
                continue
            if quality != 1:
                continue

            rec_id = row.get("id", "").strip()
            # BUT-PPG IDs: recordings are named like 100001, 100002 ...
            # subject-info uses the same IDs
            subj = subjects.get(rec_id)
            if subj is None:
                continue

            try:
                hr = float(row.get("hr", 0))
                age = float(subj.get("age_years", 0))
                gender_raw = subj.get("gender", "").strip().upper()
            except ValueError:
                continue

            if hr <= 0 or age <= 0:
                continue

            ag = _age_group(age)
            if ag is None:
                continue

            gender = "male" if gender_raw == "M" else "female" if gender_raw == "F" else None
            if gender is None:
                continue

            # Store under gender-specific and "all" buckets
            for g in (gender, "all"):
                key = (g, ag)
                hr_data.setdefault(key, []).append(hr)

    return hr_data


def build(butppg_dir: Optional[Path] = None) -> None:
    Base.metadata.create_all(bind=engine)

    # Try to load BUT-PPG data
    butppg_data: dict[tuple[str, int], list[float]] = {}
    if butppg_dir is None:
        butppg_dir = Path.home() / "Desktop" / "butppg-dataset" / \
                     "brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0"

    if butppg_dir.exists():
        try:
            butppg_data = load_butppg(butppg_dir)
            total = sum(len(v) for v in butppg_data.values())
            unique_genders = set(k[0] for k in butppg_data)
            print(f"Loaded BUT-PPG: {total} quality recordings across groups {unique_genders}")
        except Exception as e:
            print(f"Warning: Could not load BUT-PPG data ({e}). Using NHANES fallback only.")
    else:
        print(f"BUT-PPG directory not found at {butppg_dir}. Using NHANES fallback only.")

    # Build final baseline rows
    groups = [
        ("all",    20), ("all",    30), ("all",    40), ("all",    50), ("all",    60),
        ("male",   20), ("male",   30), ("male",   40), ("male",   50), ("male",   60),
        ("female", 20), ("female", 30), ("female", 40), ("female", 50), ("female", 60),
    ]

    db = SessionLocal()
    try:
        inserted = updated = 0
        for gender, age_group in groups:
            hrs = butppg_data.get((gender, age_group), [])

            if len(hrs) >= MIN_SAMPLES:
                avg_hr = statistics.mean(hrs)
                std_hr = statistics.stdev(hrs) if len(hrs) > 1 else 10.0
                n = len(hrs)
                source = f"BUT-PPG 2.0.0 (n={n}) / Takazawa 1998 b/a"
                print(f"  [{gender:6} age={age_group}] BUT-PPG n={n:3d}  "
                      f"HR={avg_hr:.1f}±{std_hr:.1f} bpm")
            else:
                fallback = NHANES_FALLBACK.get((gender, age_group))
                if fallback is None:
                    continue
                avg_hr, std_hr, n, source = fallback
                source = source + " / Takazawa 1998 b/a"
                if hrs:
                    print(f"  [{gender:6} age={age_group}] BUT-PPG only {len(hrs)} samples "
                          f"(< {MIN_SAMPLES}) → NHANES fallback")
                else:
                    print(f"  [{gender:6} age={age_group}] No BUT-PPG data → NHANES fallback")

            b_a_ref, b_a_std = TAKAZAWA_B_OVER_A.get((gender, age_group), (-0.40, 0.15))

            existing = (
                db.query(DemographicBaseline)
                .filter(DemographicBaseline.gender == gender,
                        DemographicBaseline.age_group == age_group)
                .first()
            )
            if existing:
                existing.avg_heart_rate = round(avg_hr, 1)
                existing.std_heart_rate = round(std_hr, 1)
                existing.sample_count   = n
                existing.b_over_a_ref   = b_a_ref
                existing.b_over_a_std   = b_a_std
                existing.source         = source
                updated += 1
            else:
                db.add(DemographicBaseline(
                    gender=gender, age_group=age_group,
                    avg_heart_rate=round(avg_hr, 1),
                    std_heart_rate=round(std_hr, 1),
                    sample_count=n,
                    b_over_a_ref=b_a_ref,
                    b_over_a_std=b_a_std,
                    source=source,
                ))
                inserted += 1

        db.commit()
        print(f"\nDone: {inserted} inserted, {updated} updated  ({inserted + updated} total rows)")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build demographic HR baselines")
    parser.add_argument(
        "--butppg-dir",
        type=Path,
        default=None,
        help="Path to BUT-PPG dataset root directory",
    )
    args = parser.parse_args()
    build(butppg_dir=args.butppg_dir)
