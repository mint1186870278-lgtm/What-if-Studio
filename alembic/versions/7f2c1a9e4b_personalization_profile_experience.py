"""Add authoritative user profiles and versioned creative experiences.

Revision ID: 7f2c1a9e4b
Revises: d59d2a92a78e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f2c1a9e4b"
down_revision: Union[str, Sequence[str], None] = "d59d2a92a78e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing installations have the original, small user_preferences table.
    # Batch mode keeps this migration compatible with SQLite.
    with op.batch_alter_table("user_preferences") as batch:
        batch.add_column(sa.Column("scope", sa.String(32), nullable=False, server_default="global"))
        batch.add_column(sa.Column("project_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("session_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("applicability_condition", sa.Text(), nullable=True))
        batch.add_column(sa.Column("evidence_source", sa.String(64), nullable=True))
        batch.add_column(sa.Column("evidence_ref", sa.String(255), nullable=True))
        batch.add_column(sa.Column("is_long_term", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("status", sa.String(32), nullable=False, server_default="active"))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        # confidence used to be an integer percentage.  Keep its values intact;
        # the service normalizes legacy values when reading.
        batch.alter_column("confidence", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=True)
        batch.alter_column("source", existing_type=sa.String(50), type_=sa.String(50), existing_nullable=True)

    # Backfill legacy rows so response schemas and precedence logic have
    # deterministic values.  SQLite's CURRENT_TIMESTAMP is portable enough
    # for both SQLite and PostgreSQL in this migration.
    op.execute(
        "UPDATE user_preferences SET confidence = confidence / 100.0 "
        "WHERE confidence IS NOT NULL AND confidence > 1"
    )
    op.execute(
        "UPDATE user_preferences SET scope = 'global', status = 'active', "
        "is_long_term = 1, version = 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE updated_at IS NULL"
    )

    op.create_index(
        "ix_user_preferences_lookup",
        "user_preferences",
        ["user_id", "preference_key", "scope", "status"],
        unique=False,
    )
    op.create_index("ix_user_preferences_project_id", "user_preferences", ["project_id"], unique=False)
    op.create_index("ix_user_preferences_session_id", "user_preferences", ["session_id"], unique=False)
    op.create_index("ix_user_preferences_scope", "user_preferences", ["scope"], unique=False)
    op.create_index("ix_user_preferences_status", "user_preferences", ["status"], unique=False)

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("ending_tendency", sa.String(128), nullable=True),
        sa.Column("emotional_style", sa.String(128), nullable=True),
        sa.Column("original_fidelity", sa.String(128), nullable=True),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("last_evidence_source", sa.String(64), nullable=True),
        sa.Column("last_evidence_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)

    op.create_table(
        "creative_experiences",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("applicable_condition", sa.Text(), nullable=False),
        sa.Column("advice", sa.Text(), nullable=False),
        sa.Column("user_evidence", sa.Text(), nullable=False),
        sa.Column("evidence_source", sa.String(64), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creative_experiences_user_id", "creative_experiences", ["user_id"], unique=False)
    op.create_index("ix_creative_experiences_project_id", "creative_experiences", ["project_id"], unique=False)
    op.create_index("ix_creative_experiences_session_id", "creative_experiences", ["session_id"], unique=False)
    op.create_index("ix_creative_experiences_status", "creative_experiences", ["status"], unique=False)
    op.create_index("ix_creative_experiences_lookup", "creative_experiences", ["user_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_creative_experiences_lookup", table_name="creative_experiences")
    op.drop_index("ix_creative_experiences_status", table_name="creative_experiences")
    op.drop_index("ix_creative_experiences_session_id", table_name="creative_experiences")
    op.drop_index("ix_creative_experiences_project_id", table_name="creative_experiences")
    op.drop_index("ix_creative_experiences_user_id", table_name="creative_experiences")
    op.drop_table("creative_experiences")
    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_index("ix_user_preferences_status", table_name="user_preferences")
    op.drop_index("ix_user_preferences_scope", table_name="user_preferences")
    op.drop_index("ix_user_preferences_session_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_project_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_lookup", table_name="user_preferences")
    with op.batch_alter_table("user_preferences") as batch:
        for name in (
            "updated_at", "status", "version", "is_long_term", "evidence_ref",
            "evidence_source", "applicability_condition", "session_id", "project_id", "scope",
        ):
            batch.drop_column(name)
