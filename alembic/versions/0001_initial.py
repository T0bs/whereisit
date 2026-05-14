"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'items',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'containers',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('width', sa.Float, nullable=True),
        sa.Column('height', sa.Float, nullable=True),
        sa.Column('depth', sa.Float, nullable=True),
        sa.Column('gps_lat', sa.Float, nullable=True),
        sa.Column('gps_lng', sa.Float, nullable=True),
        sa.Column('parent_id', sa.Integer, sa.ForeignKey('containers.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'item_locations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('item_id', sa.Integer, sa.ForeignKey('items.id'), nullable=False),
        sa.Column('container_id', sa.Integer, sa.ForeignKey('containers.id'), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
        sa.Column('placed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('item_locations')
    op.drop_table('containers')
    op.drop_table('items')
