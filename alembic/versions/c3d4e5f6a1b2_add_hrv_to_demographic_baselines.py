"""Add HRV columns to demographic_baselines

Revision ID: c3d4e5f6a1b2
Revises: 959e7bb7abf2
Create Date: 2026-03-03

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a1b2'
down_revision = '959e7bb7abf2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('demographic_baselines',
        sa.Column('avg_hrv_sdnn', sa.Float(), nullable=True))
    op.add_column('demographic_baselines',
        sa.Column('std_hrv_sdnn', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('demographic_baselines', 'avg_hrv_sdnn')
    op.drop_column('demographic_baselines', 'std_hrv_sdnn')
