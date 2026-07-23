"""add reading_rollups table

Revision ID: bf2c38a78f40
Revises: 17a942d570e8
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf2c38a78f40'
down_revision: Union[str, Sequence[str], None] = '17a942d570e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create reading_rollups table for F5 time-series rollups."""
    op.create_table('reading_rollups',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('sensor_type', sa.String(length=50), nullable=False),
        sa.Column('interval', sa.String(length=10), nullable=False),
        sa.Column('window_start', sa.DateTime(), nullable=False),
        sa.Column('window_end', sa.DateTime(), nullable=False),
        sa.Column('min_value', sa.Float(), nullable=False),
        sa.Column('max_value', sa.Float(), nullable=False),
        sa.Column('avg_value', sa.Float(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('anomaly_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['machine_id'], ['machines.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('machine_id', 'sensor_type', 'interval', 'window_start',
                            name='uq_rollup_machine_sensor_interval_start'),
    )
    op.create_index('ix_rollups_machine_type_window', 'reading_rollups',
                    ['machine_id', 'sensor_type', 'interval', 'window_start'], unique=False)


def downgrade() -> None:
    """Drop reading_rollups table."""
    op.drop_index('ix_rollups_machine_type_window', table_name='reading_rollups')
    op.drop_table('reading_rollups')
