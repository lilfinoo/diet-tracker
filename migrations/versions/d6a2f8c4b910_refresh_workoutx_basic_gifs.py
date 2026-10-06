"""refresh provider GIFs after upgrading WorkoutX to Basic

Revision ID: d6a2f8c4b910
Revises: c8e4a1d7f390
Create Date: 2026-10-06
"""

from alembic import op


revision = "d6a2f8c4b910"
down_revision = "c8e4a1d7f390"
branch_labels = None
depends_on = None


def upgrade():
    # Keep GIFs explicitly imported by an administrator. Provider downloads
    # are rebuilt on demand with the paid key; no user or workout data changes.
    op.execute("""
        DELETE FROM workoutx_gif
        WHERE NOT EXISTS (
            SELECT 1 FROM admin_action_audit
            WHERE action = 'exercise_media.cached'
              AND resource_type = 'exercise_media'
              AND resource_id = workoutx_gif.provider_id
        )
    """)


def downgrade():
    # Deleted cache entries are downloadable; old binary content is not restored.
    pass
