"""add mock ppg and diary tables

Revision ID: a1b2c3d4e5f6
Revises: 57c602bc5da0
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '57c602bc5da0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # mock_ppg_sources
    op.create_table(
        'mock_ppg_sources',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('record_id', sa.String(50), unique=True, nullable=False),
        sa.Column('hr_ref', sa.Float(), nullable=True),
        sa.Column('quality', sa.Integer(), server_default='1'),
        sa.Column('format', sa.String(1), nullable=True),
        sa.Column('gender', sa.String(10), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # mock_ppg_packets
    op.create_table(
        'mock_ppg_packets',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('mock_ppg_sources.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('packet_index', sa.Integer(), nullable=False),
        sa.Column('sync_byte', sa.Integer(), server_default='170'),  # 0xAA = 170
        sa.Column('packet_bytes', sa.LargeBinary(15), nullable=False),
        sa.Column('battery_level', sa.Integer(), server_default='100'),
        sa.Column('crc', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # measurement_diary
    op.create_table(
        'measurement_diary',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('measurement_id', sa.Integer(), sa.ForeignKey('measurements.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('advice', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # measurement_ppg
    op.create_table(
        'measurement_ppg',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('measurement_id', sa.Integer(), sa.ForeignKey('measurements.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('packet_index', sa.Integer(), nullable=False),
        sa.Column('sync_byte', sa.Integer(), nullable=True),
        sa.Column('packet_bytes', sa.LargeBinary(15), nullable=False),
        sa.Column('battery_level', sa.Integer(), nullable=True),
        sa.Column('crc', sa.Integer(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add mock_source_id to measurements
    # SQLite doesn't support adding FK constraints via ALTER TABLE — use batch mode
    with op.batch_alter_table('measurements') as batch_op:
        batch_op.add_column(sa.Column('mock_source_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('measurements', 'mock_source_id')
    op.drop_table('measurement_ppg')
    op.drop_table('measurement_diary')
    op.drop_table('mock_ppg_packets')
    op.drop_table('mock_ppg_sources')
