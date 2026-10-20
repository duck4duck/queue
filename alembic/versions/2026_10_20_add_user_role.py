"""add user role and nullable photo_url

Revision ID: a1b2c3d4e5f6
Revises: 9a0c15ef2722
Create Date: 2026-10-20 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9a0c15ef2722'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add role column with default 'student'
    op.add_column('users', sa.Column('role', sa.String(), server_default='student', nullable=False))
    # Make photo_url nullable
    op.alter_column('users', 'photo_url', nullable=True, existing_type=sa.String())


def downgrade() -> None:
    op.drop_column('users', 'role')
    op.alter_column('users', 'photo_url', nullable=False, existing_type=sa.String())
