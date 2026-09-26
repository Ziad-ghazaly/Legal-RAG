"""Units carry their own status (in_force/amended/repealed/suspended), legislative notes,
and their position inside the document (for the law browser).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "units", sa.Column("status", sa.String(32), nullable=False, server_default="in_force")
    )
    op.add_column("units", sa.Column("notes", sa.JSON, nullable=True))
    op.add_column("units", sa.Column("position", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_units_doc_position", "units", ["document_id", "position"])


def downgrade() -> None:
    raise NotImplementedError("forward-only")
