"""embeddings table for semantic search (M11)

Revision ID: 0002_embeddings
Revises: 0001_initial
Create Date: 2026-05-15

One row per (node, embedding_model). `vector` is JSON-serialized list of
floats — kept as TEXT to stay portable; in-Python cosine over thousands of
rows is fine for personal-scale inventory. Upgrade to pgvector / Qdrant
when scale demands.
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_embeddings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "node_id",
            sa.Integer,
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("vector", sa.Text, nullable=False),
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("node_id", "model", name="uq_embedding_node_model"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_embeddings_model", "embeddings", ["model"])


def downgrade() -> None:
    op.drop_index("ix_embeddings_model", table_name="embeddings")
    op.drop_table("embeddings")
