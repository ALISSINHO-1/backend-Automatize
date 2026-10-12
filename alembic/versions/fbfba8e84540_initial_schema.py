"""initial_schema

Revision ID: fbfba8e84540
Revises: 
Create Date: 2026-10-05 12:23:18.392529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa # type: ignore
from sqlalchemy.dialects import postgresql # type: ignore

# revision identifiers, used by Alembic.
revision: str = 'fbfba8e84540'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline do schema existente."""
    pass


def downgrade() -> None:
    """Baseline do schema existente."""
    pass
    # ### end Alembic commands ###
