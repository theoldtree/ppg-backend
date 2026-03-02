"""add_is_dev_to_measurements

Revision ID: 959e7bb7abf2
Revises: b2c3d4e5f6a1
Create Date: 2026-03-02 23:12:59.392795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '959e7bb7abf2'
down_revision: Union[str, None] = 'b2c3d4e5f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('measurements') as batch_op:
        batch_op.add_column(sa.Column('is_dev', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('measurements') as batch_op:
        batch_op.drop_column('is_dev')
