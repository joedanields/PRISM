"""add sensor_health table with proper schema

Revision ID: 402a10f6c87e
Revises: 797b920f4a2a
Create Date: 2026-07-23 23:16:24.637743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '402a10f6c87e'
down_revision: Union[str, Sequence[str], None] = '797b920f4a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sensor_health table (ORM-managed version)."""
    op.create_table('sensor_health',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('sensor_type', sa.String(length=50), nullable=False),
        sa.Column('health_percentage', sa.Float(), server_default=sa.text('100.0')),
        sa.Column('last_updated', sa.DateTime()),
        sa.Column('status', sa.String(length=20), server_default='healthy'),
        sa.Column('created_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('machine_id', 'sensor_type', name='uq_sensor_health_machine_sensor'),
    )


def downgrade() -> None:
    """Drop sensor_health table."""
    op.drop_table('sensor_health')
