"""add users_cart table

Revision ID: 930420394ede
Revises: 9175dde3d3c8
Create Date: 2026-09-29 15:08:48.530097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '930420394ede'
down_revision: Union[str, Sequence[str], None] = '9175dde3d3c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users_cart',
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('appid', sa.BigInteger(), nullable=False),
    sa.Column('checkout_key', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['appid'], ['store_games.appid'], ),
    sa.ForeignKeyConstraint(['username'], ['auth_users.username'], ),
    sa.PrimaryKeyConstraint('username', 'appid')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('users_cart')
