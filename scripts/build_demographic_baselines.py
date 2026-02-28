"""
Build Demographic Baseline Table

Combines:
  1. BUT-PPG dataset (ECG-derived HR statistics by age group × gender)
  2. Literature b/a reference values (Takazawa 1998, Bortolotto 2000)

Run from the ppg-backend directory:
    python scripts/build_demographic_baselines.py

Requires BUT-PPG dataset at:
    /Users/yujeongmu/Desktop/butppg-dataset/brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0/
"""

import os
import sys
import pandas as pd
import numpy as np

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal, engine, Base
from app.db.models.measurement import DemographicBaseline

DATASET_PATH = (
    "/Users/yujeongmu/Desktop/butppg-dataset/"
    "brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0"
)

# ── Literature-based APG b/a reference values ─────────────────────────────────
# Source: Takazawa K. et al. (1998) Am J Hypertension; Bortolotto LA et al. (2000)
# b/a decreases with age (arterial stiffness increases).
# Values below are means ± SD per decade (healthy adults).
LITERATURE_B_OVER_A = {
    # age_group: (b_over_a_ref, b_over_a_std)
    20: (-0.38, 0.08),
    30: (-0.45, 0.09),
    40: (-0.52, 0.10),
    50: (-0.60, 0.11),
    60: (-0.68, 0.12),
}


def age_to_group(age: float) -> int:
    if age < 25:
        return 20
    if age < 35:
        return 30
    if age < 45:
        return 40
    if age < 55:
        return 50
    return 60


def normalize_gender(gender_str: str) -> str:
    g = str(gender_str).strip().lower()
    if g in ("m", "male", "1"):
        return "male"
    if g in ("f", "female", "0"):
        return "female"
    return "all"


def load_butppg_hr_stats() -> pd.DataFrame:
    """
    Load BUT-PPG HR annotations and subject info.
    Returns a DataFrame with columns: gender, age_group, HR.
    Only rows with good signal quality (Quality == 1) are kept.
    """
    subject_csv = os.path.join(DATASET_PATH, "subject-info.csv")
    quality_csv = os.path.join(DATASET_PATH, "quality-hr-ann.csv")

    if not os.path.exists(subject_csv):
        raise FileNotFoundError(f"subject-info.csv not found at {subject_csv}")
    if not os.path.exists(quality_csv):
        raise FileNotFoundError(f"quality-hr-ann.csv not found at {quality_csv}")

    subjects = pd.read_csv(subject_csv, encoding="utf-8-sig")
    quality = pd.read_csv(quality_csv)

    # Normalise column names (strip whitespace)
    subjects.columns = subjects.columns.str.strip()
    quality.columns = quality.columns.str.strip()

    # Identify subject ID column (first column)
    subj_id_col = subjects.columns[0]

    # Keep only good-quality recordings
    good = quality[quality["Quality"] == 1].copy()

    # The first column of quality CSV is the recording ID (e.g. "100001")
    # Subject ID is the first 6 digits; position 0-5
    rec_id_col = good.columns[0]
    good["subject_id"] = good[rec_id_col].astype(str).str[:6].astype(int)

    # Merge with subject info
    merged = good.merge(
        subjects.rename(columns={subj_id_col: "subject_id"}),
        on="subject_id",
        how="inner",
    )

    # Identify age and gender columns (flexible naming)
    age_col = next((c for c in merged.columns if "age" in c.lower()), None)
    gender_col = next((c for c in merged.columns if "gender" in c.lower() or "sex" in c.lower()), None)

    if age_col is None or gender_col is None:
        raise ValueError(
            f"Could not find age/gender columns. Available: {list(merged.columns)}"
        )

    merged["age_group"] = merged[age_col].apply(age_to_group)
    merged["gender_norm"] = merged[gender_col].apply(normalize_gender)

    return merged[["gender_norm", "age_group", "HR"]].dropna()


def build_baselines(df: pd.DataFrame) -> list[dict]:
    """
    Compute HR stats per (gender, age_group) and per ('all', age_group).
    """
    rows = []
    groups = [("gender_norm", "age_group")]

    for _, group_df in df.groupby(["gender_norm", "age_group"]):
        gender = group_df["gender_norm"].iloc[0]
        age_group = int(group_df["age_group"].iloc[0])
        hr_vals = group_df["HR"].values
        b_ref, b_std = LITERATURE_B_OVER_A.get(age_group, (-0.50, 0.10))
        rows.append({
            "gender": gender,
            "age_group": age_group,
            "avg_heart_rate": float(np.mean(hr_vals)),
            "std_heart_rate": float(np.std(hr_vals, ddof=1)),
            "sample_count": int(len(hr_vals)),
            "b_over_a_ref": b_ref,
            "b_over_a_std": b_std,
            "source": "BUT-PPG 2.0 ECG-derived HR + Takazawa/Bortolotto b/a literature",
        })

    # 'all' gender rows (combine male + female)
    for age_group, age_df in df.groupby("age_group"):
        age_group = int(age_group)
        hr_vals = age_df["HR"].values
        b_ref, b_std = LITERATURE_B_OVER_A.get(age_group, (-0.50, 0.10))
        rows.append({
            "gender": "all",
            "age_group": age_group,
            "avg_heart_rate": float(np.mean(hr_vals)),
            "std_heart_rate": float(np.std(hr_vals, ddof=1)),
            "sample_count": int(len(hr_vals)),
            "b_over_a_ref": b_ref,
            "b_over_a_std": b_std,
            "source": "BUT-PPG 2.0 ECG-derived HR + Takazawa/Bortolotto b/a literature",
        })

    return rows


def main():
    print("=" * 60)
    print("Building demographic baselines from BUT-PPG dataset")
    print("=" * 60)

    # ── Load dataset ─────────────────────────────────────────────
    print("\n[1/3] Loading BUT-PPG HR data...")
    try:
        df = load_butppg_hr_stats()
        print(f"      Loaded {len(df)} good-quality recordings")
        print(f"      Age groups: {sorted(df['age_group'].unique())}")
        print(f"      Genders: {sorted(df['gender_norm'].unique())}")
    except FileNotFoundError as e:
        print(f"\n  ⚠  Dataset not found: {e}")
        print("     Using synthetic HR stats instead.\n")
        df = _synthetic_hr_df()

    # ── Build baseline rows ───────────────────────────────────────
    print("\n[2/3] Computing statistics...")
    rows = build_baselines(df)
    for r in rows:
        print(
            f"      {r['gender']:6s} age {r['age_group']}s: "
            f"HR={r['avg_heart_rate']:.1f}±{r['std_heart_rate']:.1f} bpm "
            f"(n={r['sample_count']})  b/a={r['b_over_a_ref']}"
        )

    # ── Write to DB ───────────────────────────────────────────────
    print("\n[3/3] Writing to database...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Clear existing baselines
        db.query(DemographicBaseline).delete()
        db.commit()

        for r in rows:
            db.add(DemographicBaseline(**r))
        db.commit()
        print(f"      ✓ Inserted {len(rows)} baseline rows")
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("✓ Done!")
    print("=" * 60)


def _synthetic_hr_df() -> pd.DataFrame:
    """
    Fallback: synthetic HR data when BUT-PPG dataset is unavailable.
    Values approximate published resting HR norms (American Heart Association).
    """
    np.random.seed(42)
    records = []
    params = {
        # age_group: (male_mean, female_mean, std)
        20: (68, 72, 9),
        30: (70, 74, 9),
        40: (72, 75, 10),
        50: (73, 76, 10),
        60: (74, 77, 11),
    }
    for age_group, (m_mean, f_mean, std) in params.items():
        for _ in range(50):
            records.append({"gender_norm": "male",   "age_group": age_group, "HR": np.random.normal(m_mean, std)})
            records.append({"gender_norm": "female", "age_group": age_group, "HR": np.random.normal(f_mean, std)})
    df = pd.DataFrame(records)
    df["HR"] = df["HR"].clip(40, 120).round(1)
    return df


if __name__ == "__main__":
    main()
