"""Add indexes to notifications table for efficient queries

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-03-08

Adds composite indexes:
  - (user_id, created_at DESC) for listing newest-first
  - (user_id, is_read) for unread count queries
"""
from alembic import op

revision = 'f6a1b2c3d4e5'
down_revision = 'e5f6a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_notifications_user_created',
        'notifications',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_notifications_user_is_read',
        'notifications',
        ['user_id', 'is_read'],
    )


def downgrade() -> None:
    op.drop_index('ix_notifications_user_is_read', table_name='notifications')
    op.drop_index('ix_notifications_user_created', table_name='notifications')
