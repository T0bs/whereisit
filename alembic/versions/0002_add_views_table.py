"""add views table and link containers

Revision ID: 0002_add_views_table
Revises: 0001_initial
Create Date: 2026-01-14 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_views_table'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Create views table
    op.create_table(
        'views',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
    )

    # Add nullable view_id to containers
    op.add_column('containers', sa.Column('view_id', sa.Integer(), nullable=True))

    # Insert default view rows
    op.execute("INSERT INTO views (name) VALUES ('front')")
    op.execute("INSERT INTO views (name) VALUES ('top')")

    # Set existing containers to 'front'
    op.execute("UPDATE containers SET view_id = (SELECT id FROM views WHERE name='front')")

    # Make view_id non-nullable and add foreign key
    op.alter_column('containers', 'view_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key('fk_containers_view', 'containers', 'views', ['view_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_containers_view', 'containers', type_='foreignkey')
    op.drop_column('containers', 'view_id')
    op.drop_table('views')
