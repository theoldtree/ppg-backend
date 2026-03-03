"""Consolidate measurements: merge analysis_results into measurements, drop unused tables

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-03-03

Changes:
- Add analysis columns to measurements (heart_rate, hrv_sdnn, hrv_rmssd, pi, ac, dc,
  apg_b_over_a, apg_c_over_a, apg_d_over_a, stress_level, result_status)
- Migrate existing analysis_results rows into measurements
- Drop: analysis_results, measurement_diary, measurement_ppg, ppg_processed_data
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a1b2c3'
down_revision = 'c3d4e5f6a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add analysis columns to measurements ──────────────────────────────
    with op.batch_alter_table('measurements') as batch_op:
        batch_op.add_column(sa.Column('heart_rate',    sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('hrv_sdnn',      sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('hrv_rmssd',     sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('pi',            sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ac',            sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('dc',            sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('apg_b_over_a',  sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('apg_c_over_a',  sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('apg_d_over_a',  sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('stress_level',  sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('result_status', sa.String(20), nullable=True))

    # ── 2. Migrate analysis_results → measurements ───────────────────────────
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT measurement_id, heart_rate, hrv_sdnn, hrv_rmssd, pi, ac, dc, "
        "       apg_b_over_a, apg_c_over_a, apg_d_over_a, stress_level, status "
        "FROM analysis_results"
    )).fetchall()

    for row in rows:
        conn.execute(sa.text(
            "UPDATE measurements SET "
            "  heart_rate=:hr, hrv_sdnn=:sdnn, hrv_rmssd=:rmssd, "
            "  pi=:pi, ac=:ac, dc=:dc, "
            "  apg_b_over_a=:b_a, apg_c_over_a=:c_a, apg_d_over_a=:d_a, "
            "  stress_level=:stress, result_status=:status "
            "WHERE id=:mid"
        ), {
            "hr": row[1], "sdnn": row[2], "rmssd": row[3],
            "pi": row[4], "ac": row[5], "dc": row[6],
            "b_a": row[7], "c_a": row[8], "d_a": row[9],
            "stress": row[10], "status": row[11],
            "mid": row[0],
        })

    # ── 3. Migrate measurement_diary → measurements ──────────────────────────
    diary_rows = conn.execute(sa.text(
        "SELECT measurement_id, notes, tags, advice FROM measurement_diary"
    )).fetchall()

    for row in diary_rows:
        conn.execute(sa.text(
            "UPDATE measurements SET notes=:notes, tags=:tags, advice=:advice "
            "WHERE id=:mid AND (notes IS NULL OR notes = '')"
        ), {"notes": row[1], "tags": row[2], "advice": row[3], "mid": row[0]})

    # ── 4. Drop unused tables ─────────────────────────────────────────────────
    op.drop_table('ppg_processed_data')
    op.drop_table('measurement_ppg')
    op.drop_table('measurement_diary')
    op.drop_table('analysis_results')


def downgrade() -> None:
    # Recreate dropped tables (empty — data migration is not reversible)
    op.create_table(
        'analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('measurement_id', sa.Integer(), nullable=False),
        sa.Column('heart_rate', sa.Float(), nullable=True),
        sa.Column('hrv_sdnn', sa.Float(), nullable=True),
        sa.Column('hrv_rmssd', sa.Float(), nullable=True),
        sa.Column('hrv_pnn50', sa.Float(), nullable=True),
        sa.Column('apg_b_over_a', sa.Float(), nullable=True),
        sa.Column('apg_c_over_a', sa.Float(), nullable=True),
        sa.Column('apg_d_over_a', sa.Float(), nullable=True),
        sa.Column('apg_e_over_a', sa.Float(), nullable=True),
        sa.Column('stress_level', sa.Float(), nullable=True),
        sa.Column('z_score', sa.Float(), nullable=True),
        sa.Column('is_anomaly', sa.Boolean(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('pi', sa.Float(), nullable=True),
        sa.Column('ac', sa.Float(), nullable=True),
        sa.Column('dc', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['measurement_id'], ['measurements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'measurement_diary',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('measurement_id', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('advice', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['measurement_id'], ['measurements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('measurement_id'),
    )
    op.create_table(
        'measurement_ppg',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('measurement_id', sa.Integer(), nullable=False),
        sa.Column('packet_index', sa.Integer(), nullable=False),
        sa.Column('sync_byte', sa.Integer(), nullable=True),
        sa.Column('packet_bytes', sa.LargeBinary(length=15), nullable=False),
        sa.Column('battery_level', sa.Integer(), nullable=True),
        sa.Column('crc', sa.Integer(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['measurement_id'], ['measurements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'ppg_processed_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('measurement_id', sa.Integer(), nullable=False),
        sa.Column('window_start', sa.Float(), nullable=False),
        sa.Column('window_end', sa.Float(), nullable=False),
        sa.Column('window_type', sa.String(length=20), nullable=False),
        sa.Column('mean_value', sa.Float(), nullable=True),
        sa.Column('std_dev', sa.Float(), nullable=True),
        sa.Column('peak_count', sa.Integer(), nullable=True),
        sa.Column('snr', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['measurement_id'], ['measurements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('measurements') as batch_op:
        batch_op.drop_column('result_status')
        batch_op.drop_column('stress_level')
        batch_op.drop_column('apg_d_over_a')
        batch_op.drop_column('apg_c_over_a')
        batch_op.drop_column('apg_b_over_a')
        batch_op.drop_column('dc')
        batch_op.drop_column('ac')
        batch_op.drop_column('pi')
        batch_op.drop_column('hrv_rmssd')
        batch_op.drop_column('hrv_sdnn')
        batch_op.drop_column('heart_rate')
