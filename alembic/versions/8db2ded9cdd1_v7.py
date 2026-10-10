"""v7

Revision ID: 8db2ded9cdd1
Revises: 7cbb685e0ec2
Create Date: 2025-04-30 12:44:33.883927

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8db2ded9cdd1'
down_revision: Union[str, None] = '7cbb685e0ec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Drop any existing unique constraint to avoid conflicts
    op.execute("ALTER TABLE console_users DROP CONSTRAINT IF EXISTS uq_partner_maglo_publisher")
    
    # Drop any existing index to avoid naming conflicts
    op.execute("DROP INDEX IF EXISTS uq_partner_maglo_publisher")
    
    # Create the partial unique index (idempotent if already exists)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_partner_maglo_publisher 
        ON console_users (partner_id)
        WHERE is_maglo_publisher = True
    """)

def downgrade() -> None:
    # Drop the partial unique index
    op.execute("DROP INDEX IF EXISTS uq_partner_maglo_publisher")
    
    # Optionally recreate the original unique constraint (may fail if duplicates exist)
    op.create_unique_constraint('uq_partner_maglo_publisher', 'console_users', ['partner_id', 'is_maglo_publisher'])