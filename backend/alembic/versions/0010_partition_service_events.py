"""Partition service_events by year on PostgreSQL (P4 scale finding).

The build audit's number was 1.8 million components; a fleet at that scale
plausibly logs tens of millions of service events over its lifetime. A
single unpartitioned table still answers correctly at that size, but every
query, index rebuild, and vacuum pays the cost of the *entire* history even
when - as with ``dashboard.monthly_activity`` (see app/api/dashboard.py) -
the caller only wants a recent window. Range-partitioning by
``event_date`` lets Postgres prune to the relevant partition(s) before
touching a row, and lets old partitions be archived or dropped independently
of the live table.

Deliberately Postgres-only and a no-op everywhere else
--------------------------------------------------------------------------
SQLite (every test run, every local dev environment without Docker) has no
native table partitioning, so this migration is a guarded no-op there - the
``if bind.dialect.name != "postgresql": return`` below. The ORM model
(``app/models/service_event.py``) is intentionally left declaring a single-
column primary key: application code never needs to know the physical
storage is partitioned, only Postgres's own catalog does, and every INSERT
still returns its generated ``id`` via ``RETURNING`` exactly as before.

Why service_events and not audit_logs
--------------------------------------------------------------------------
``audit_logs`` is the other obvious "event table" candidate and grows just
as fast, but Postgres requires a partitioned table's primary key and unique
constraints to *include* the partition key - here, that would force
``current_hash`` (currently globally unique) into a
``(current_hash, timestamp)`` constraint, which is a materially different
uniqueness guarantee on the one table in this system where an untested
change to a uniqueness guarantee is least acceptable. That trade was judged
not worth it for this pass; `docs/database-scale.md` records the decision
so it is a documented choice, not a silent gap.

Revision ID: 0010_partition_service_events
Revises: 0009_tenancy
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = '0010_partition_service_events'
down_revision: Union[str, None] = '0009_tenancy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Wide enough to cover every plausible installation date in the seeded demo
#: fleet (components can be decades old) plus headroom forward. Anything
#: outside this range lands in the DEFAULT partition rather than failing an
#: insert - a missing future partition should never block writes.
_FIRST_YEAR = 2000
_LAST_YEAR = 2036


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    op.execute("ALTER TABLE service_events RENAME TO service_events_legacy")
    op.execute("ALTER INDEX ix_service_events_component_id RENAME TO ix_service_events_component_id_legacy")
    op.execute("ALTER INDEX ix_service_events_event_type RENAME TO ix_service_events_event_type_legacy")
    op.execute("ALTER INDEX ix_service_events_event_date RENAME TO ix_service_events_event_date_legacy")
    op.execute(
        "ALTER INDEX ix_service_events_component_date "
        "RENAME TO ix_service_events_component_date_legacy"
    )

    op.execute(
        """
        CREATE TABLE service_events (
            id INTEGER NOT NULL,
            component_id INTEGER NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            event_date DATE NOT NULL,
            technician VARCHAR(96),
            description TEXT,
            operating_hours FLOAT,
            vibration FLOAT,
            temperature FLOAT,
            inspection_score FLOAT,
            created_at TIMESTAMP NOT NULL,
            PRIMARY KEY (id, event_date)
        ) PARTITION BY RANGE (event_date)
        """
    )

    op.execute("CREATE TABLE service_events_default PARTITION OF service_events DEFAULT")
    for year in range(_FIRST_YEAR, _LAST_YEAR):
        op.execute(
            f"""
            CREATE TABLE service_events_y{year} PARTITION OF service_events
            FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')
            """
        )

    op.execute("INSERT INTO service_events SELECT * FROM service_events_legacy")

    # The id sequence already exists (owned by the legacy table's column);
    # re-point its ownership and this table's default at it so autoincrement
    # keeps working, instead of Postgres creating - and this table quietly
    # diverging onto - a second identity sequence.
    op.execute(
        """
        DO $$
        DECLARE
            seq_name text;
        BEGIN
            SELECT pg_get_serial_sequence('service_events_legacy', 'id') INTO seq_name;
            IF seq_name IS NOT NULL THEN
                EXECUTE format('ALTER SEQUENCE %s OWNED BY service_events.id', seq_name);
                EXECUTE format(
                    'ALTER TABLE service_events ALTER COLUMN id SET DEFAULT nextval(%L)', seq_name
                );
                PERFORM setval(seq_name, COALESCE((SELECT MAX(id) FROM service_events), 1));
            END IF;
        END $$;
        """
    )

    op.execute(
        "ALTER TABLE service_events ADD CONSTRAINT fk_service_events_component "
        "FOREIGN KEY (component_id) REFERENCES components (id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX ix_service_events_component_id ON service_events (component_id)")
    op.execute("CREATE INDEX ix_service_events_event_type ON service_events (event_type)")
    op.execute("CREATE INDEX ix_service_events_event_date ON service_events (event_date)")
    op.execute(
        "CREATE INDEX ix_service_events_component_date ON service_events (component_id, event_date)"
    )

    op.execute("DROP TABLE service_events_legacy")


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("ALTER TABLE service_events RENAME TO service_events_partitioned")
    op.execute(
        """
        CREATE TABLE service_events (
            id SERIAL PRIMARY KEY,
            component_id INTEGER NOT NULL REFERENCES components (id) ON DELETE CASCADE,
            event_type VARCHAR(32) NOT NULL,
            event_date DATE NOT NULL,
            technician VARCHAR(96),
            description TEXT,
            operating_hours FLOAT,
            vibration FLOAT,
            temperature FLOAT,
            inspection_score FLOAT,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("INSERT INTO service_events SELECT * FROM service_events_partitioned")
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('service_events', 'id'),
            COALESCE((SELECT MAX(id) FROM service_events), 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_service_events_component_id ON service_events (component_id)")
    op.execute("CREATE INDEX ix_service_events_event_type ON service_events (event_type)")
    op.execute("CREATE INDEX ix_service_events_event_date ON service_events (event_date)")
    op.execute(
        "CREATE INDEX ix_service_events_component_date ON service_events (component_id, event_date)"
    )
    op.execute("DROP TABLE service_events_partitioned")
