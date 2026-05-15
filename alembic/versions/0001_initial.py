"""initial unified-nodes schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-15

Creates the unified hierarchical model: kinds (reference), nodes (the tree),
tags + node_tags (many-to-many), property_keys (reference) + node_properties
(key-value). FULLTEXT index on nodes(name, description) is the foundation for
the M5 search endpoint. Seeds kinds with sensible defaults.
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kinds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(50), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=False),
    )

    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "kind_id",
            sa.Integer,
            sa.ForeignKey("kinds.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Integer,
            sa.ForeignKey("nodes.id"),
            nullable=True,
        ),
        sa.Column(
            "can_contain",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "quantity",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("width", sa.Float, nullable=True),
        sa.Column("height", sa.Float, nullable=True),
        sa.Column("depth", sa.Float, nullable=True),
        sa.Column("weight", sa.Float, nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lng", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        mysql_engine="InnoDB",
    )
    # MySQL FULLTEXT index — keyword search foundation for M5.
    op.execute(
        "CREATE FULLTEXT INDEX ft_nodes_name_description "
        "ON nodes (name, description)"
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )

    op.create_table(
        "node_tags",
        sa.Column(
            "node_id",
            sa.Integer,
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer,
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "property_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "value_type",
            sa.Enum("string", "int", "float", "bool", name="value_type_enum"),
            nullable=False,
            server_default="string",
        ),
    )

    op.create_table(
        "node_properties",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "node_id",
            sa.Integer,
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "key_id",
            sa.Integer,
            sa.ForeignKey("property_keys.id"),
            nullable=False,
        ),
        sa.Column("value", sa.Text, nullable=False),
        sa.UniqueConstraint("node_id", "key_id", name="uq_node_property"),
    )

    kinds_table = sa.table(
        "kinds", sa.column("slug", sa.String), sa.column("label", sa.String)
    )
    op.bulk_insert(
        kinds_table,
        [
            {"slug": "room", "label": "Room"},
            {"slug": "building", "label": "Building"},
            {"slug": "cupboard", "label": "Cupboard"},
            {"slug": "shelf", "label": "Shelf"},
            {"slug": "drawer", "label": "Drawer"},
            {"slug": "box", "label": "Box"},
            {"slug": "bag", "label": "Bag"},
            {"slug": "item", "label": "Item"},
            {"slug": "tool", "label": "Tool"},
            {"slug": "consumable", "label": "Consumable"},
        ],
    )


def downgrade() -> None:
    op.drop_table("node_properties")
    op.drop_table("property_keys")
    op.drop_table("node_tags")
    op.drop_table("tags")
    op.drop_table("nodes")
    op.drop_table("kinds")
