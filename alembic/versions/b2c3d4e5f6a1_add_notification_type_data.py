"""add notification type and data_json columns

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(50), nullable=False, server_default='measurement_complete'))
        batch_op.add_column(sa.Column('data_json', sa.Text(), nullable=True))
        batch_op.create_index('ix_notifications_user_id', ['user_id'])


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_index('ix_notifications_user_id')
        batch_op.drop_column('data_json')
        batch_op.drop_column('type')
