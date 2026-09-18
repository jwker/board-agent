"""init

Revision ID: dfda2922d8d2
Revises:
Create Date: 2026-09-18 13:10:10.639966

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "dfda2922d8d2"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
