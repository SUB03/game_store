"""drop users_cart checkout_key

Revision ID: 3d1247a63876
Revises: 930420394ede
Create Date: 2026-10-09 10:34:39.865053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d1247a63876'
down_revision: Union[str, Sequence[str], None] = '930420394ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users_cart', 'checkout_key')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'users_cart',
        sa.Column('checkout_key', sa.Text(), nullable=False, server_default=''),
    )
