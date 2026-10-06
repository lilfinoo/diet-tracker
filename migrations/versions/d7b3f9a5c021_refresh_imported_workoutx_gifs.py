"""refresh manually imported Free-tier WorkoutX GIFs

Revision ID: d7b3f9a5c021
Revises: d6a2f8c4b910
Create Date: 2026-10-06
"""

from alembic import op


revision = "d7b3f9a5c021"
down_revision = "d6a2f8c4b910"
branch_labels = None
depends_on = None


def upgrade():
    # Production checks confirmed that old administrative imports also contain
    # Free-tier watermarks. Retain their audit trail, then download paid GIFs.
    op.execute("""
        DELETE FROM workoutx_gif
        WHERE EXISTS (
            SELECT 1 FROM admin_action_audit
            WHERE action = 'exercise_media.cached'
              AND resource_type = 'exercise_media'
              AND resource_id = workoutx_gif.provider_id
        )
    """)


def downgrade():
    pass
