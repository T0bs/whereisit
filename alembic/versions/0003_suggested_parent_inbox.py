"""suggested_parent_id column + inbox kind (M13)

Revision ID: 0003_suggested_parent_inbox
Revises: 0002_embeddings
Create Date: 2026-05-16

Adds the M13 plumbing for the bulk-add / suggest-category flow:

- New nullable column nodes.suggested_parent_id (FK to nodes.id). Single
  pending suggestion per item; cleared when the user accepts the move.
  ON DELETE SET NULL so deleting a candidate parent doesn't cascade.
- New kind slug "inbox" used for the lazily-created top-level
  "Uncategorized" container. The container itself is NOT seeded here —
  the bulk-add endpoint creates it on first use so empty DBs stay empty.
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_suggested_parent_inbox"
down_revision = "0002_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("suggested_parent_id", sa.Integer, nullable=True),
    )
    op.create_foreign_key(
        "fk_nodes_suggested_parent",
        "nodes",
        "nodes",
        ["suggested_parent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    kinds_table = sa.table(
        "kinds", sa.column("slug", sa.String), sa.column("label", sa.String)
    )
    op.bulk_insert(kinds_table, [{"slug": "inbox", "label": "Inbox"}])


def downgrade() -> None:
    op.drop_constraint("fk_nodes_suggested_parent", "nodes", type_="foreignkey")
    op.drop_column("nodes", "suggested_parent_id")
    op.execute("DELETE FROM kinds WHERE slug = 'inbox'")
