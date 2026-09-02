from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Sequence

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import engine


ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[1] / "alembic.ini"
LOCAL_DATABASE_HOSTS = frozenset({"db", "localhost", "127.0.0.1"})
RESET_CONFIRMATION_PREFIX = "RESET:"
RESET_SQL = ("DROP SCHEMA public CASCADE", "CREATE SCHEMA public")


class SchemaErrorCode(StrEnum):
    SCHEMA_VERSION_TABLE_MISSING = "schema_version_table_missing"
    SCHEMA_REVISION_MISSING = "schema_revision_missing"
    SCHEMA_REVISION_OUTDATED = "schema_revision_outdated"
    SCHEMA_MULTIPLE_HEADS = "schema_multiple_heads"
    SCHEMA_UNREACHABLE = "schema_unreachable"
    RESET_TARGET_FORBIDDEN = "reset_target_forbidden"
    RESET_CONFIRMATION_MISMATCH = "reset_confirmation_mismatch"
    RESET_PARTIAL_FAILURE = "reset_partial_failure"


class SchemaControlError(RuntimeError):
    def __init__(
        self,
        code: SchemaErrorCode,
        *,
        current_revision: str | None = None,
        expected_revision: str | None = None,
    ) -> None:
        self.code = code.value
        self.current_revision = current_revision
        self.expected_revision = expected_revision
        details = [self.code]
        if current_revision is not None:
            details.append(f"current={current_revision}")
        if expected_revision is not None:
            details.append(f"expected={expected_revision}")
        super().__init__("; ".join(details))


@dataclass(frozen=True)
class SchemaReadiness:
    current_revision: str
    expected_revision: str


@dataclass(frozen=True)
class ResetPlan:
    app_env: str
    dialect: str
    host: str
    port: int | None
    database: str
    current_revision: str
    target_revision: str
    row_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ResetResult:
    database: str
    previous_revision: str
    current_revision: str
    deleted_rows: int


def _resolve_code_heads() -> tuple[str, ...]:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    script = ScriptDirectory.from_config(config)
    return tuple(script.get_heads())


async def _read_database_revisions() -> tuple[str, ...] | None:
    async with engine.connect() as connection:
        version_table = await connection.scalar(
            text("SELECT to_regclass('public.alembic_version')")
        )
        if version_table is None:
            return None
        result = await connection.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        )
        return tuple(str(row[0]) for row in result.all())


async def require_current_schema() -> SchemaReadiness:
    code_heads = _resolve_code_heads()
    if len(code_heads) != 1:
        raise SchemaControlError(SchemaErrorCode.SCHEMA_MULTIPLE_HEADS)
    expected_revision = code_heads[0]

    try:
        database_revisions = await _read_database_revisions()
    except SchemaControlError:
        raise
    except Exception:
        raise SchemaControlError(
            SchemaErrorCode.SCHEMA_UNREACHABLE,
            expected_revision=expected_revision,
        ) from None

    if database_revisions is None:
        raise SchemaControlError(
            SchemaErrorCode.SCHEMA_VERSION_TABLE_MISSING,
            expected_revision=expected_revision,
        )
    if not database_revisions:
        raise SchemaControlError(
            SchemaErrorCode.SCHEMA_REVISION_MISSING,
            expected_revision=expected_revision,
        )
    if len(database_revisions) != 1:
        raise SchemaControlError(
            SchemaErrorCode.SCHEMA_MULTIPLE_HEADS,
            current_revision=",".join(database_revisions),
            expected_revision=expected_revision,
        )

    current_revision = database_revisions[0]
    if current_revision != expected_revision:
        raise SchemaControlError(
            SchemaErrorCode.SCHEMA_REVISION_OUTDATED,
            current_revision=current_revision,
            expected_revision=expected_revision,
        )
    return SchemaReadiness(
        current_revision=current_revision,
        expected_revision=expected_revision,
    )


async def plan_local_reset(expected_database: str) -> ResetPlan:
    raise SchemaControlError(SchemaErrorCode.RESET_TARGET_FORBIDDEN)


async def execute_local_reset(
    plan: ResetPlan,
    *,
    confirmation: str,
) -> ResetResult:
    raise SchemaControlError(SchemaErrorCode.RESET_TARGET_FORBIDDEN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check or reset the application schema.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Require the database to be at the code head.")

    reset = subparsers.add_parser("reset", help="Preview or execute an exact local reset.")
    reset.add_argument("--expected-database", required=True)
    reset.add_argument("--execute", action="store_true")
    reset.add_argument("--confirm")
    return parser


async def _run_command(args: argparse.Namespace) -> int:
    if args.command == "check":
        readiness = await require_current_schema()
        print(f"PASS: schema current; revision={readiness.current_revision}")
        return 0

    plan = await plan_local_reset(args.expected_database)
    if not args.execute:
        print(
            "PREVIEW: "
            f"env={plan.app_env} dialect={plan.dialect} host={plan.host} "
            f"port={plan.port} database={plan.database} "
            f"current={plan.current_revision} target={plan.target_revision}"
        )
        for table_name, row_count in plan.row_counts:
            print(f"table={table_name} rows={row_count}")
        return 0

    result = await execute_local_reset(plan, confirmation=args.confirm or "")
    print(
        f"PASS: reset complete; database={result.database} "
        f"revision={result.current_revision} deleted_rows={result.deleted_rows}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run_command(args))
    except SchemaControlError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
