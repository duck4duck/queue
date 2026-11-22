"""subject_table5

Revision ID: c73c881a66e8
Revises: ac49edf0837d
Create Date: 2026-02-18 00:26:32.871933

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c73c881a66e8'
down_revision: Union[str, Sequence[str], None] = 'ac49edf0837d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve users while advancing the migration chain.
    pass

def downgrade() -> None:
    # This historical migration no longer performs destructive changes.
    pass
