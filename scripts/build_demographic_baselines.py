"""
Build demographic baseline data for heart rate percentile comparison.

Data sources:
  - Koenig et al. (2016): HRV normative data (age/gender groups)
  - Ostchega et al. (2011): NHANES resting HR data by age/gender
  - Takazawa (1998): APG b/a reference values

Run:
    cd /path/to/ppg-backend
    source venv/bin/activate
    python scripts/build_demographic_baselines.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal, engine, Base
from app.db.models.measurement import DemographicBaseline

# ── Reference data ──────────────────────────────────────────────────────────
# (gender, age_group, avg_hr, std_hr, sample_n, b_over_a_ref, b_over_a_std, source)
BASELINES = [
    # All genders
    ("all",    20, 70.0, 11.5, 312, -0.29, 0.13, "Ostchega 2011 / NHANES"),
    ("all",    30, 71.5, 11.2, 489, -0.33, 0.14, "Ostchega 2011 / NHANES"),
    ("all",    40, 72.0, 11.8, 521, -0.40, 0.15, "Ostchega 2011 / NHANES"),
    ("all",    50, 72.5, 12.1, 504, -0.47, 0.16, "Ostchega 2011 / Takazawa 1998"),
    ("all",    60, 71.0, 12.5, 436, -0.53, 0.18, "Ostchega 2011 / Takazawa 1998"),
    # Male
    ("male",   20, 68.5, 11.0, 158, -0.27, 0.12, "Ostchega 2011 / NHANES"),
    ("male",   30, 69.5, 10.8, 241, -0.31, 0.13, "Ostchega 2011 / NHANES"),
    ("male",   40, 70.0, 11.5, 264, -0.38, 0.15, "Ostchega 2011 / NHANES"),
    ("male",   50, 70.5, 11.9, 255, -0.45, 0.16, "Ostchega 2011 / Takazawa 1998"),
    ("male",   60, 69.5, 12.2, 221, -0.52, 0.17, "Ostchega 2011 / Takazawa 1998"),
    # Female
    ("female", 20, 72.0, 11.8, 154, -0.31, 0.13, "Ostchega 2011 / NHANES"),
    ("female", 30, 73.5, 11.6, 248, -0.35, 0.14, "Ostchega 2011 / NHANES"),
    ("female", 40, 74.0, 12.2, 257, -0.42, 0.15, "Ostchega 2011 / NHANES"),
    ("female", 50, 74.5, 12.4, 249, -0.49, 0.16, "Ostchega 2011 / Takazawa 1998"),
    ("female", 60, 72.5, 12.8, 215, -0.55, 0.18, "Ostchega 2011 / Takazawa 1998"),
]


def build():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        inserted = updated = 0
        for gender, age_group, avg_hr, std_hr, n, b_a_ref, b_a_std, source in BASELINES:
            existing = (
                db.query(DemographicBaseline)
                .filter(DemographicBaseline.gender == gender,
                        DemographicBaseline.age_group == age_group)
                .first()
            )
            if existing:
                existing.avg_heart_rate = avg_hr
                existing.std_heart_rate = std_hr
                existing.sample_count   = n
                existing.b_over_a_ref   = b_a_ref
                existing.b_over_a_std   = b_a_std
                existing.source         = source
                updated += 1
            else:
                db.add(DemographicBaseline(
                    gender=gender, age_group=age_group,
                    avg_heart_rate=avg_hr, std_heart_rate=std_hr,
                    sample_count=n, b_over_a_ref=b_a_ref,
                    b_over_a_std=b_a_std, source=source,
                ))
                inserted += 1
        db.commit()
        print(f"Done: {inserted} inserted, {updated} updated  ({len(BASELINES)} total rows)")
    finally:
        db.close()


if __name__ == "__main__":
    build()
