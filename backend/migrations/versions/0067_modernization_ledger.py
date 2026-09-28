"""Track 3: the Module Migration Ledger — one row per legacy module, and the state machine
every agent moves it through (research §5.2, Flow document §20.3).

    assessed → designed → sequenced → baselined → migrating → in_review → verifying
             → verified → cut_over → retired            (and `blocked` from any state)

WHY A TABLE, NOT ANOTHER JSONB COLUMN. Many agents write it — Review and Security at the same
moment — it is queried per module ("which modules in wave 2 are not verified?"), and it is the
audit record. The artifacts hold the CONTENT; the ledger holds the STATE and the POINTERS.

THE MACHINE IS ENFORCED IN THE DATABASE, not only in the service. A trigger refuses:
  * a state change the machine does not allow (the list below mirrors
    `shared/services/modernization_ledger.ALLOWED`; a test pins them together);
  * a state change that does not append exactly one history entry;
  * any update that drops or rewrites an existing history entry (append-only).
Which AGENT may make which transition is the service's job (a database row does not know which
agent is asking); the database guarantees that no path — a bug, a script, a hand-written UPDATE —
skips a state or loses history.

DELETE IS NOT BLOCKED here: rows go with their project (ON DELETE CASCADE), and the test
suite's tenant cleanup deletes by tenant. The service simply has no delete.

FORCE ROW LEVEL SECURITY on `app.current_tenant_id` (Lessons R18) — the same policy shape as
0065.

Revision ID: 0067_modernization_ledger
Revises: 0066_track3_owner_rows
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0067_modernization_ledger"
down_revision = "0066_track3_owner_rows"
branch_labels = None
depends_on = None

TABLE = "modernization_modules"

STATES = ("assessed", "designed", "sequenced", "baselined", "migrating", "in_review",
          "verifying", "verified", "cut_over", "retired", "blocked")

#: (from, to). `blocked` is reachable from every state but `retired`; leaving `blocked` is
#: checked separately (only back to the state it was blocked from, or to `migrating`).
TRANSITIONS = (
    ("assessed", "designed"),
    ("designed", "sequenced"),
    ("sequenced", "baselined"),
    ("baselined", "migrating"),
    ("migrating", "in_review"),
    ("in_review", "verifying"),
    ("in_review", "migrating"),
    ("verifying", "verified"),
    ("verifying", "migrating"),
    ("verified", "cut_over"),
    ("cut_over", "verified"),      # a rollback: back on legacy, still proven
    ("cut_over", "retired"),
    ("verified", "migrating"),     # reopen (research §12.4), reason required
    ("cut_over", "migrating"),     # reopen
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("module_id", sa.String(16), nullable=False),
        sa.Column("module_name", sa.String(255), nullable=False),
        sa.Column("legacy_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("tier", sa.String(16)),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("patterns", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("contract_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("adr_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("wave", sa.String(8)),
        sa.Column("ec_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("baseline_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("target_path", sa.Text()),
        sa.Column("target_branch", sa.Text()),
        sa.Column("pr_url", sa.Text()),
        sa.Column("review_verdict", sa.String(24)),
        sa.Column("security_verdict", sa.String(16)),
        sa.Column("equivalence_verdict", sa.String(16)),
        sa.Column("perf_verdict", sa.String(16)),
        sa.Column("cutover_state", sa.String(24)),
        sa.Column("decommission_date", sa.Date()),
        sa.Column("rejection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("blocked_from", sa.String(16)),
        sa.Column("blocked_reason", sa.Text()),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("state_changed_by", sa.String(255)),
        sa.Column("history", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "module_id", name="uq_modernization_module"),
        sa.CheckConstraint("state IN (" + ",".join(f"'{s}'" for s in STATES) + ")", name="ck_ledger_state"),
        sa.CheckConstraint("module_id ~ '^M-[0-9]{2,}$'", name="ck_ledger_module_id"),
        sa.CheckConstraint("jsonb_typeof(history) = 'array'", name="ck_ledger_history_array"),
        sa.CheckConstraint("(state = 'blocked') = (blocked_from IS NOT NULL)", name="ck_ledger_blocked_from"),
    )

    allowed = " OR ".join(f"(OLD.state = '{a}' AND NEW.state = '{b}')" for a, b in TRANSITIONS)
    op.execute(f"""
        CREATE OR REPLACE FUNCTION modernization_ledger_guard() RETURNS trigger AS $$
        DECLARE
            old_len int := jsonb_array_length(OLD.history);
            new_len int := jsonb_array_length(NEW.history);
            i int;
        BEGIN
            -- Append-only history: every existing entry kept, in place, unchanged.
            IF new_len < old_len THEN
                RAISE EXCEPTION 'ledger history is append-only (% entries became %)', old_len, new_len
                    USING ERRCODE = 'check_violation';
            END IF;
            FOR i IN 0 .. old_len - 1 LOOP
                IF NEW.history -> i IS DISTINCT FROM OLD.history -> i THEN
                    RAISE EXCEPTION 'ledger history is append-only (entry % was changed)', i
                        USING ERRCODE = 'check_violation';
                END IF;
            END LOOP;

            IF NEW.state IS DISTINCT FROM OLD.state THEN
                IF new_len <> old_len + 1 THEN
                    RAISE EXCEPTION 'a ledger state change must append exactly one history entry'
                        USING ERRCODE = 'check_violation';
                END IF;
                IF NEW.state = 'blocked' THEN
                    IF OLD.state = 'retired' THEN
                        RAISE EXCEPTION 'a retired module cannot be blocked' USING ERRCODE = 'check_violation';
                    END IF;
                ELSIF OLD.state = 'blocked' THEN
                    IF NOT (NEW.state = OLD.blocked_from OR NEW.state = 'migrating') THEN
                        RAISE EXCEPTION 'a blocked module returns to % or to migrating, not %',
                            OLD.blocked_from, NEW.state USING ERRCODE = 'check_violation';
                    END IF;
                ELSIF NOT ({allowed}) THEN
                    RAISE EXCEPTION 'illegal ledger transition % -> %', OLD.state, NEW.state
                        USING ERRCODE = 'check_violation';
                END IF;
            ELSIF new_len <> old_len AND NEW.state = OLD.state AND new_len > old_len + 1 THEN
                RAISE EXCEPTION 'at most one history entry per update' USING ERRCODE = 'check_violation';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"CREATE TRIGGER modernization_ledger_guard BEFORE UPDATE ON {TABLE} "
               "FOR EACH ROW EXECUTE FUNCTION modernization_ledger_guard()")
    op.execute(f"""
        CREATE OR REPLACE FUNCTION modernization_ledger_insert_guard() RETURNS trigger AS $$
        BEGIN
            IF NEW.state NOT IN ('assessed', 'designed') THEN
                RAISE EXCEPTION 'a module enters the ledger as assessed or designed, not %', NEW.state
                    USING ERRCODE = 'check_violation';
            END IF;
            IF jsonb_array_length(NEW.history) <> 1 THEN
                RAISE EXCEPTION 'a new ledger row carries exactly its creation entry'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"CREATE TRIGGER modernization_ledger_insert_guard BEFORE INSERT ON {TABLE} "
               "FOR EACH ROW EXECUTE FUNCTION modernization_ledger_insert_guard()")

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {TABLE} "
               "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)")
    op.execute(f"CREATE POLICY tenant_isolation_insert ON {TABLE} "
               "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sdlc_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO sdlc_app;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS modernization_ledger_guard ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS modernization_ledger_insert_guard ON {TABLE}")
    op.execute("DROP FUNCTION IF EXISTS modernization_ledger_guard()")
    op.execute("DROP FUNCTION IF EXISTS modernization_ledger_insert_guard()")
    op.drop_table(TABLE)
