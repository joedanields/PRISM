"""add source and quality columns to sensor_readings

Revision ID: e779e724d869
Revises: bf2c38a78f40
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e779e724d869'
down_revision: Union[str, Sequence[str], None] = 'bf2c38a78f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """F4: Add source and quality columns to sensor_readings."""
    op.add_column('sensor_readings',
        sa.Column('source', sa.String(length=20), server_default='simulator'))
    op.add_column('sensor_readings',
        sa.Column('quality', sa.String(length=10), server_default='good'))


def downgrade() -> None:
    """Remove source and quality columns."""
    op.drop_column('sensor_readings', 'quality')
    op.drop_column('sensor_readings', 'source')
