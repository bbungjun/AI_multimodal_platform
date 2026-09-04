"""Fixed G5C1 PostgreSQL proof, executed as stdin in an owned migrate container."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from uuid import UUID

ACCOUNTING = (
    "credit_reservations",
    "credit_reservation_items",
    "credit_reservation_allocations",
    "credit_usage_records",
)
HEAD = "0006_credit_accounting_persistence"
NOW = datetime(2024, 4, 1, 9, tzinfo=timezone.utc)
phase = "guard"


def uid(number):
    return UUID(int=60000 + number)


def validate_target(project, url, provider, app_env, database):
    if (not re.fullmatch(r"schema-verify-[a-z0-9]{8,32}", project)
            or url.get_backend_name() != "postgresql" or url.host != "db"
            or not database or url.database != database
            or provider != "mock" or app_env != "test"):
        raise ValueError("accounting_schema_target_refused")


async def migrate(target, expected=None):
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "downgrade", target,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        output, error = await asyncio.wait_for(process.communicate(), 30)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.communicate()
        raise
    if expected is None:
        assert process.returncode == 0, "accounting_migration_failed"
    else:
        assert process.returncode != 0 and expected.encode() in output + error, "accounting_migration_refusal_missing"


async def snapshot(connection):
    return tuple([
        await connection.fetchval(f"SELECT count(*) FROM {table}")
        for table in ACCOUNTING
    ])


async def seed_prerequisites(connection):
    for number in (1, 2):
        await connection.execute(
            "INSERT INTO users(id,email_verified,role,status,data_origin,signed_up_at,updated_at) "
            "VALUES($1,false,'user','active','synthetic',$2,$2)", uid(number), NOW)
        await connection.execute(
            "INSERT INTO credit_accounts(user_id,cycle_anchor_at,plan,created_at,updated_at) "
            "VALUES($1,$2,'free',$2,$2)", uid(number), NOW)
        await connection.execute(
            "INSERT INTO credit_cycles(id,user_id,cycle_index,starts_at,ends_at,plan,allowance_microcredits,created_at) "
            "VALUES($1,$2,0,$3,$4,'free',1000000000,$3)",
            uid(10 + number), uid(number), NOW, NOW + timedelta(days=30))
        await connection.execute(
            "INSERT INTO credit_grants(id,user_id,cycle_id,kind,created_at,expires_at,"
            "granted_microcredits,reserved_microcredits,consumed_microcredits,expired_microcredits,reason_code) "
            "VALUES($1,$2,$3,'base',$4,$5,1000000000,0,0,0,'cycle_base')",
            uid(20 + number), uid(number), uid(10 + number), NOW, NOW + timedelta(days=30))


def reservation(number=30, user=1, **overrides):
    values = dict(id=uid(number), user_id=uid(user), reserve_operation_key=f"reserve_{number}",
                  rate_card_version="v1", status="held", reserved_microcredits=50_000_000,
                  created_at=NOW, terminal_operation_key=None, terminal_at=None,
                  terminal_reason_code=None, delivery=None)
    values.update(overrides)
    return values


def item(reservation_id=uid(30), user=1, **overrides):
    values = dict(reservation_id=reservation_id, user_id=uid(user), meter="imagen_fast_image",
                  maximum_units=1, quoted_microcredits=50_000_000)
    values.update(overrides)
    return values


def allocation(reservation_id=uid(30), user=1, grant_id=uid(21), **overrides):
    values = dict(reservation_id=reservation_id, grant_id=grant_id, user_id=uid(user),
                  ordinal=0, reserved_microcredits=50_000_000)
    values.update(overrides)
    return values


def usage(reservation_id=uid(30), user=1, **overrides):
    values = dict(reservation_id=reservation_id, meter="imagen_fast_image", user_id=uid(user),
                  terminal_operation_key="terminal_30", rate_card_version="v1", actual_units=1,
                  charged_microcredits=50_000_000, recorded_at=NOW, source="mock_estimate",
                  delivery="delivered")
    values.update(overrides)
    return values


async def insert(connection, table, values):
    assert table in ACCOUNTING
    columns = ",".join(values)
    placeholders = ",".join(f"${index}" for index in range(1, len(values) + 1))
    return await connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", *values.values())


async def prove_constraints(connection):
    import asyncpg
    checks = 0

    async def reject_insert(table, values, sqlstate, constraint=None):
        nonlocal checks
        before = await snapshot(connection)
        transaction = connection.transaction()
        await transaction.start()
        try:
            try:
                await insert(connection, table, values)
            except asyncpg.PostgresError as error:
                assert error.sqlstate == sqlstate
                if constraint:
                    assert error.constraint_name == constraint
            else:
                raise AssertionError("accounting_constraint_missing")
        finally:
            await transaction.rollback()
        assert await snapshot(connection) == before
        checks += 1

    async def reject_sql(sql, code):
        nonlocal checks
        before = await snapshot(connection)
        transaction = connection.transaction()
        await transaction.start()
        try:
            try:
                await connection.execute(sql)
            except asyncpg.CheckViolationError as error:
                assert str(error) == code
            else:
                raise AssertionError("accounting_mutation_guard_missing")
        finally:
            await transaction.rollback()
        assert await snapshot(connection) == before
        checks += 1

    outer = connection.transaction()
    await outer.start()
    try:
        await seed_prerequisites(connection)
        await insert(connection, "credit_reservations", reservation())
        await insert(connection, "credit_reservation_items", item())
        await insert(connection, "credit_reservation_allocations", allocation())

        for change in (
            dict(reserved_microcredits=0), dict(reserve_operation_key="unsafe key"),
            dict(rate_card_version="v0"), dict(status="bad"),
            dict(terminal_operation_key="terminal_held"),
            dict(status="settled", terminal_operation_key="terminal_bad", terminal_at=NOW,
                 terminal_reason_code="usage_settled", delivery="no_deliverable"),
            dict(status="released", terminal_operation_key="terminal_bad", terminal_at=NOW - timedelta(seconds=1),
                 terminal_reason_code="provider_failed", delivery="no_deliverable"),
            dict(status="released", terminal_operation_key="terminal_bad", terminal_at=NOW,
                 terminal_reason_code="unsafe reason", delivery="no_deliverable"),
        ):
            await reject_insert("credit_reservations", reservation(31, **change), "23514")
        await reject_insert("credit_reservations", reservation(31, reserve_operation_key="reserve_30"), "23505")
        await reject_insert("credit_reservations", reservation(31, user=9), "23503")

        for change in (dict(meter="unknown"), dict(maximum_units=0), dict(quoted_microcredits=0)):
            await reject_insert("credit_reservation_items", item(**change), "23514")
        await reject_insert("credit_reservation_items", item(user=2), "23503", "fk_credit_reservation_items_owner")

        for change in (dict(ordinal=-1), dict(reserved_microcredits=0)):
            await reject_insert("credit_reservation_allocations", allocation(grant_id=uid(22), **change), "23514")
        await reject_insert("credit_reservation_allocations", allocation(user=2, ordinal=1), "23503", "fk_credit_reservation_allocations_owner")
        await reject_insert("credit_reservation_allocations", allocation(grant_id=uid(22), ordinal=1), "23503", "fk_credit_reservation_allocations_grant_owner")

        for change in (
            dict(terminal_operation_key="unsafe key"), dict(rate_card_version="v0"),
            dict(actual_units=-1), dict(charged_microcredits=-1), dict(source="unknown"),
            dict(delivery="unknown"), dict(delivery="no_deliverable", charged_microcredits=1),
        ):
            await reject_insert("credit_usage_records", usage(**change), "23514")
        await reject_insert("credit_usage_records", usage(user=2), "23503", "fk_credit_usage_records_item_owner")

        await insert(connection, "credit_usage_records", usage())
        await connection.execute(
            "UPDATE credit_reservations SET status='settled',terminal_operation_key='terminal_30',"
            "terminal_at=$1,terminal_reason_code='usage_settled',delivery='delivered' WHERE id=$2", NOW, uid(30))
        checks += 2
        await insert(connection, "credit_reservations", reservation(
            32, reserve_operation_key="reserve_32", reserved_microcredits=10,
            status="released", terminal_operation_key="terminal_32", terminal_at=NOW,
            terminal_reason_code="provider_failed", delivery="no_deliverable"))
        await reject_insert("credit_reservations", reservation(
            33, reserve_operation_key="reserve_33", status="released",
            terminal_operation_key="terminal_30", terminal_at=NOW,
            terminal_reason_code="provider_failed", delivery="no_deliverable"), "23505")

        await reject_sql("UPDATE credit_reservations SET reserved_microcredits=1 WHERE id='00000000-0000-0000-0000-00000000ea7e'", "credit_reservation_immutable")
        await reject_sql("UPDATE credit_reservations SET delivery='partial' WHERE id='00000000-0000-0000-0000-00000000ea7e'", "credit_reservation_immutable")
        await reject_sql("DELETE FROM credit_reservations WHERE id='00000000-0000-0000-0000-00000000ea7e'", "credit_reservation_immutable")
        await reject_sql("TRUNCATE credit_reservations CASCADE", "credit_reservation_immutable")
        for table in ACCOUNTING[1:]:
            await reject_sql(f"UPDATE {table} SET user_id=user_id", "credit_accounting_append_only")
            await reject_sql(f"DELETE FROM {table}", "credit_accounting_append_only")
            await reject_sql(f"TRUNCATE {table} CASCADE", "credit_accounting_append_only")
    finally:
        await outer.rollback()
    assert await snapshot(connection) == (0, 0, 0, 0)
    return checks


async def prove_metadata():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine
    import app.credit_models
    import app.models
    from app.db import Base
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata))
            assert not differences, "accounting_metadata_mismatch"
    finally:
        await engine.dispose()


async def prove_downgrade(connection):
    global phase
    phase = "downgrade"
    transaction = connection.transaction()
    await transaction.start()
    await connection.execute("LOCK TABLE credit_reservations IN ROW EXCLUSIVE MODE")
    try:
        await migrate("0005_credit_lifecycle_operations", "lock timeout")
    finally:
        await transaction.rollback()
    await seed_prerequisites(connection)
    await insert(connection, "credit_reservations", reservation())
    await insert(connection, "credit_reservation_items", item())
    await insert(connection, "credit_reservation_allocations", allocation())
    await insert(connection, "credit_usage_records", usage())
    before = await snapshot(connection)
    await migrate("0005_credit_lifecycle_operations", "credit_accounting_requires_empty_tables")
    assert await snapshot(connection) == before
    assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
    return 4


async def main():
    import asyncpg
    from sqlalchemy.engine import make_url
    global phase
    url = make_url(os.environ.get("DATABASE_URL", ""))
    validate_target(os.environ.get("ACCOUNTING_SCHEMA_PROJECT", ""), url,
                    os.environ.get("AI_PROVIDER"), os.environ.get("APP_ENV"),
                    os.environ.get("ACCOUNTING_SCHEMA_DATABASE"))
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg:", "postgresql:")
    connection = await asyncpg.connect(dsn)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == HEAD
        phase = "metadata"
        await prove_metadata()
        phase = "constraints"
        checks = await prove_constraints(connection)
        downgrade_cases = await prove_downgrade(connection)
        phase = "done"
        print(json.dumps({"groups": 4, "checks": checks, "downgrade_cases": downgrade_cases}))
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("accounting_schema_proof_failed:" + phase)
        sys.exit(124)
    except Exception:
        print("accounting_schema_proof_failed:" + phase)
        sys.exit(1)
