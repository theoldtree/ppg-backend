"""Add Welford M2 columns to user_baselines and demographic_baselines

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-03-03

Adds m2_heart_rate and m2_hrv_sdnn (Welford sum-of-squared-deviations) so
std = sqrt(M2 / (n-1)) can be computed without storing all raw values.

Also initialises M2 from existing std and sample_count:
  M2 = std^2 * (n - 1)
"""
from alembic import op
import sqlalchemy as sa
import math


revision = 'e5f6a1b2c3d4'
down_revision = 'd4e5f6a1b2c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── user_baselines ────────────────────────────────────────────────────────
    with op.batch_alter_table('user_baselines') as batch_op:
        batch_op.add_column(sa.Column('m2_heart_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('m2_hrv_sdnn',   sa.Float(), nullable=True))

    # Initialise M2 from existing std / count
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, std_heart_rate, std_hrv_sdnn, measurement_count FROM user_baselines"
    )).fetchall()
    for row in rows:
        n = row[3] or 0
        if n > 1:
            m2_hr  = (row[1] ** 2) * (n - 1) if row[1] else None
            m2_hrv = (row[2] ** 2) * (n - 1) if row[2] else None
            conn.execute(sa.text(
                "UPDATE user_baselines SET m2_heart_rate=:m2hr, m2_hrv_sdnn=:m2hrv WHERE id=:id"
            ), {"m2hr": m2_hr, "m2hrv": m2_hrv, "id": row[0]})

    # ── demographic_baselines ─────────────────────────────────────────────────
    with op.batch_alter_table('demographic_baselines') as batch_op:
        batch_op.add_column(sa.Column('m2_heart_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('m2_hrv_sdnn',   sa.Float(), nullable=True))

    rows = conn.execute(sa.text(
        "SELECT id, std_heart_rate, std_hrv_sdnn, sample_count FROM demographic_baselines"
    )).fetchall()
    for row in rows:
        n = row[3] or 0
        if n > 1:
            m2_hr  = (row[1] ** 2) * (n - 1) if row[1] else None
            m2_hrv = (row[2] ** 2) * (n - 1) if row[2] else None
            conn.execute(sa.text(
                "UPDATE demographic_baselines SET m2_heart_rate=:m2hr, m2_hrv_sdnn=:m2hrv WHERE id=:id"
            ), {"m2hr": m2_hr, "m2hrv": m2_hrv, "id": row[0]})


def downgrade() -> None:
    with op.batch_alter_table('demographic_baselines') as batch_op:
        batch_op.drop_column('m2_hrv_sdnn')
        batch_op.drop_column('m2_heart_rate')

    with op.batch_alter_table('user_baselines') as batch_op:
        batch_op.drop_column('m2_hrv_sdnn')
        batch_op.drop_column('m2_heart_rate')
