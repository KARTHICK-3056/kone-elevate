#!/usr/bin/env python
"""Bulk-seed a large synthetic fleet directly in SQL, then benchmark the API.

The build audit's number was 1.8 million components and tens of millions of
service events - the number P4's "load-test at fleet scale" deliverable
says the system should be tested at. This script is the honest version of
that: it seeds a large fleet with plain SQL (not the ORM per-row inference
path `scripts/seed_database.py` uses, which is the right tool for a curated
demo fleet and the wrong one for a million rows) and benchmarks the
endpoints the P4 SQL-aggregation rewrite (see app/api/dashboard.py) was
about.

Two subcommands:
    python scripts/load_test.py seed --count 200000
    python scripts/load_test.py bench --base-url http://localhost:8000 \\
        --email supervisor@kone-elevate.demo --password elevate-demo-2026

**What this does and does not prove.** It genuinely measures the SQL
aggregation queries against a real Postgres instance at whatever --count is
run with, in whatever environment this script executes in. It does NOT
reproduce 1.8 million components in this repository's CI or development
environment - that is a real infrastructure commitment (disk, seed time,
a provisioned database) beyond what a prototype's throwaway container
should carry. Treat the numbers this prints as evidence that the query
shape is now O(distinct groups) / O(indexed row range) rather than
O(fleet size) - which is what actually determines whether it survives
a 30x larger fleet - not as a certification that 1.8M itself was tested.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.utils.enums import ComponentType, Material, Recommendation, ServiceEventType  # noqa: E402

COMPONENT_TYPES = ComponentType.values()
MATERIALS = Material.values()
RECOMMENDATIONS = [r for r in Recommendation.values() if r != Recommendation.DEFER_TO_INSPECTION.value]
EVENT_TYPES = ServiceEventType.values()
COUNTRIES = [("India", "Chennai"), ("India", "Bengaluru"), ("Germany", "Berlin"), ("UAE", "Dubai")]


def _sql_array(values) -> str:
    return "ARRAY[" + ",".join(f"'{v}'" for v in values) + "]"


def seed(count: int, events_per_component: int) -> None:
    """Bulk-insert `count` components, one prediction and N events each.

    Pure SQL, no ORM object construction - the only way inserting a few
    hundred thousand rows finishes in seconds rather than hours. Skips the
    audit chain and material-flow ledger on purpose: those are per-row,
    hash-chained, deliberately serial writes (see app.services.audit_service)
    that a bulk load has no business going through, the same way a real
    ETL/bulk-import job into an audited table would use a separate,
    reviewed bulk path rather than the interactive write API.
    """
    types_arr = _sql_array(COMPONENT_TYPES)
    materials_arr = _sql_array(MATERIALS)
    recs_arr = _sql_array(RECOMMENDATIONS)
    countries_arr = "ARRAY[" + ",".join(f"'{c}'" for c, _ in COUNTRIES) + "]"
    units_arr = "ARRAY[" + ",".join(f"'{u}'" for _, u in COUNTRIES) + "]"
    events_arr = _sql_array(EVENT_TYPES)

    started = time.perf_counter()
    with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect != "postgresql":
            print(
                f"load_test.py seed requires PostgreSQL (DATABASE_URL is '{dialect}'). "
                "Point DATABASE_URL at the docker-compose Postgres instance.",
                file=sys.stderr,
            )
            raise SystemExit(2)

        base = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM components")).scalar_one()
        conn.execute(
            text(
                f"""
                INSERT INTO components (
                    component_id, serial_number, component_type, material, manufacturer, origin,
                    installation_date, operating_hours, load_cycles, average_load, vibration,
                    temperature, service_count, repair_count, failure_history, inspection_score,
                    health_score, current_status, location, qr_token, country, frontline_unit,
                    created_at, updated_at
                )
                SELECT
                    'LOAD-' || (n + :base),
                    'LOADSN-' || (n + :base),
                    t.component_type,
                    t.material,
                    'Load Test Manufacturer',
                    'Load Test Plant',
                    CURRENT_DATE - ((random() * 7300)::int),
                    (random() * 60000)::float,
                    (random() * 300000)::int,
                    (200 + random() * 800)::float,
                    (random() * 8)::float,
                    (20 + random() * 60)::float,
                    (random() * 20)::int,
                    (random() * 5)::int,
                    (random() * 3)::int,
                    (random() * 100)::float,
                    (random() * 100)::float,
                    'ACTIVE',
                    c.frontline_unit || ', ' || c.country,
                    'LOADQR-' || (n + :base),
                    c.country,
                    c.frontline_unit,
                    now(),
                    now()
                FROM generate_series(1, :count) AS n
                CROSS JOIN LATERAL (
                    SELECT ({types_arr})[1 + floor(random() * {len(COMPONENT_TYPES)})::int] AS component_type,
                           ({materials_arr})[1 + floor(random() * {len(MATERIALS)})::int] AS material
                ) t
                CROSS JOIN LATERAL (
                    SELECT ({countries_arr})[idx] AS country, ({units_arr})[idx] AS frontline_unit
                    FROM (SELECT 1 + floor(random() * {len(COUNTRIES)})::int AS idx) pick
                ) c
                """
            ),
            {"base": base, "count": count},
        )

        conn.execute(
            text(
                f"""
                INSERT INTO predictions (
                    component_id, health_score, recommendation, underlying_recommendation,
                    abstained, confidence, model_version, key_factors, input_snapshot,
                    probabilities, safety_flag, safety_message, predicted_at
                )
                SELECT
                    c.id,
                    c.health_score,
                    ({recs_arr})[1 + floor(random() * {len(RECOMMENDATIONS)})::int],
                    ({recs_arr})[1 + floor(random() * {len(RECOMMENDATIONS)})::int],
                    false,
                    (0.5 + random() * 0.5)::float,
                    'load-test-synthetic',
                    '[]'::jsonb,
                    '{{}}'::jsonb,
                    '{{}}'::jsonb,
                    false,
                    NULL,
                    now()
                FROM components c
                WHERE c.component_id LIKE 'LOAD-%'
                AND c.id > :base
                """
            ),
            {"base": base},
        )

        conn.execute(
            text(
                f"""
                INSERT INTO service_events (
                    component_id, event_type, event_date, technician, description,
                    operating_hours, vibration, temperature, inspection_score, created_at
                )
                SELECT
                    c.id,
                    ({events_arr})[1 + floor(random() * {len(EVENT_TYPES)})::int],
                    CURRENT_DATE - ((random() * 3650)::int),
                    'load-test-script',
                    'Bulk load-test event',
                    (random() * 60000)::float,
                    (random() * 8)::float,
                    (20 + random() * 60)::float,
                    (random() * 100)::float,
                    now()
                FROM components c
                CROSS JOIN generate_series(1, :n_events)
                WHERE c.component_id LIKE 'LOAD-%'
                AND c.id > :base
                """
            ),
            {"base": base, "n_events": events_per_component},
        )

    elapsed = time.perf_counter() - started
    print(
        f"Seeded {count:,} components (+predictions, +{events_per_component}x "
        f"service events) in {elapsed:.1f}s"
    )

    with SessionLocal() as session:
        total = session.execute(text("SELECT count(*) FROM components")).scalar_one()
        events = session.execute(text("SELECT count(*) FROM service_events")).scalar_one()
        print(f"Fleet now has {total:,} components and {events:,} service events total.")


def _percentile(values, pct: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    index = min(len(values) - 1, int(len(values) * pct))
    return values[index]


def _timed_get(url: str, token: str) -> float:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        exc.read()
    return time.perf_counter() - started


def bench(base_url: str, email: str, password: str, repeats: int) -> None:
    login_request = urllib.request.Request(
        f"{base_url}/api/v1/auth/login",
        data=f"username={email}&password={password}".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    import json

    with urllib.request.urlopen(login_request, timeout=30) as response:
        token = json.loads(response.read())["access_token"]

    endpoints = {
        "dashboard/summary (all_units=true)": f"{base_url}/api/v1/dashboard/summary?all_units=true",
        "dashboard/analytics (all_units=true)": f"{base_url}/api/v1/dashboard/analytics?all_units=true",
        "dashboard/safety-queue (all_units=true)": f"{base_url}/api/v1/dashboard/safety-queue?all_units=true",
        "components list (page_size=50)": f"{base_url}/api/v1/components?page_size=50",
        "forecast/capacity": f"{base_url}/api/v1/forecast/capacity",
    }

    print(f"{'endpoint':<42}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'max ms':>10}")
    for name, url in endpoints.items():
        samples = [_timed_get(url, token) * 1000 for _ in range(repeats)]
        print(
            f"{name:<42}{statistics.median(samples):>10.1f}"
            f"{_percentile(samples, 0.95):>10.1f}{_percentile(samples, 0.99):>10.1f}{max(samples):>10.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seed_parser = sub.add_parser("seed", help="Bulk-insert a large synthetic fleet")
    seed_parser.add_argument("--count", type=int, default=100_000)
    seed_parser.add_argument("--events-per-component", type=int, default=3)

    bench_parser = sub.add_parser("bench", help="Time key endpoints against a running API")
    bench_parser.add_argument("--base-url", default="http://localhost:8000")
    bench_parser.add_argument("--email", default="supervisor@kone-elevate.demo")
    bench_parser.add_argument("--password", default="elevate-demo-2026")
    bench_parser.add_argument("--repeats", type=int, default=15)

    args = parser.parse_args()
    if args.command == "seed":
        seed(args.count, args.events_per_component)
    else:
        bench(args.base_url, args.email, args.password, args.repeats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
