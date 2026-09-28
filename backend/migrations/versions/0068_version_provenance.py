"""Track 3 backbone on the version store: what a version was built from, what it restores,
and who approved it in which capacity.

Three additions to `artifact_versions` (0045), all NULLABLE so every existing row — every
Track 1 version — reads exactly as before:

  built_from        [{artifact, stage, version, status, commit?}] — the inputs this version
                    was built from, pinned at freeze time (research §5.3 "the envelope").
                    Staleness is computed from it: an input with a newer PUBLISHED version
                    makes this one stale; a newer draft does not.
  restored_from,    a restore (research §12.4) is a NEW version whose content is an earlier
  restore_reason    one; these say which, and why. A restore never mutates the old version.
  approved_as,      who approved in which capacity (research §12.2): "owner", or
  fallback_reason   "fallback:project_admin" — which must carry a reason (a DB CHECK).

The first three are PROVENANCE and join the freeze trigger's write-once list; `approved_as`
and `fallback_reason` are LIFECYCLE (set when the version is published), like `published_by`.

Revision ID: 0068_version_provenance
Revises: 0067_modernization_ledger
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0068_version_provenance"
down_revision = "0067_modernization_ledger"
branch_labels = None
depends_on = None

_TABLE = "artifact_versions"

_FREEZE_COLUMNS_0045 = ("payload", "content_hash", "project_id", "tenant_id", "stage", "version",
                        "covers", "produced_by", "created_at")
_FREEZE_COLUMNS_0068 = _FREEZE_COLUMNS_0045 + ("built_from", "restored_from", "restore_reason")


def _freeze_function(columns: tuple[str, ...]) -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in columns)
    return f"""
        CREATE OR REPLACE FUNCTION artifact_versions_freeze()
        RETURNS TRIGGER AS $$
        BEGIN
            IF {changed}
            THEN
                RAISE EXCEPTION
                    'artifact_versions row % is frozen: payload, hash, identity, covers and '
                    'provenance cannot be modified after creation (attempted on stage %, '
                    'version %)', OLD.id, OLD.stage, OLD.version
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("built_from", postgresql.JSONB(), nullable=True))
    op.add_column(_TABLE, sa.Column("restored_from", sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("restore_reason", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("approved_as", sa.String(32), nullable=True))
    op.add_column(_TABLE, sa.Column("fallback_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_artifact_versions_built_from_array", _TABLE,
        "built_from IS NULL OR jsonb_typeof(built_from) = 'array'")
    op.create_check_constraint(
        "ck_artifact_versions_restore_has_reason", _TABLE,
        "restored_from IS NULL OR (restore_reason IS NOT NULL AND length(btrim(restore_reason)) > 0)")
    op.create_check_constraint(
        "ck_artifact_versions_approved_as", _TABLE,
        "approved_as IS NULL OR approved_as IN ('owner', 'fallback:project_admin')")
    op.create_check_constraint(
        "ck_artifact_versions_fallback_has_reason", _TABLE,
        "approved_as IS DISTINCT FROM 'fallback:project_admin' "
        "OR (fallback_reason IS NOT NULL AND length(btrim(fallback_reason)) > 0)")
    op.execute(_freeze_function(_FREEZE_COLUMNS_0068))


def downgrade() -> None:
    op.execute(_freeze_function(_FREEZE_COLUMNS_0045))
    for name in ("ck_artifact_versions_fallback_has_reason", "ck_artifact_versions_approved_as",
                 "ck_artifact_versions_restore_has_reason", "ck_artifact_versions_built_from_array"):
        op.drop_constraint(name, _TABLE, type_="check")
    for column in ("fallback_reason", "approved_as", "restore_reason", "restored_from", "built_from"):
        op.drop_column(_TABLE, column)
