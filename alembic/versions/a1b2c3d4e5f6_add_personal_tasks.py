"""add_personal_tasks

Revision ID: a1b2c3d4e5f6
Revises: d8ff1092fce2
Create Date: 2026-04-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd8ff1092fce2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'personal_tasks',
        sa.Column('task_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('location', sa.String(256), nullable=True),
        sa.Column('is_done', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_personal_tasks_user_id', 'personal_tasks', ['user_id'])
    op.create_index('ix_personal_tasks_start_time', 'personal_tasks', ['start_time'])


def downgrade() -> None:
    op.drop_index('ix_personal_tasks_start_time', table_name='personal_tasks')
    op.drop_index('ix_personal_tasks_user_id', table_name='personal_tasks')
    op.drop_table('personal_tasks')
