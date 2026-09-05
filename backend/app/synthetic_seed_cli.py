"""Explicit disposable-target CLI; preview is a full transaction rollback."""
import argparse
import asyncio
from datetime import datetime
import json
import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import AsyncSessionLocal, close_db_connection
from app.synthetic_seed import SeedError, instant, seed_fixture


def validate_target(settings, expected_database, execute, confirmation):
    try:
        url = make_url(settings.database_url)
        if (not re.fullmatch(r"master_seed_verify_[a-f0-9]{12}", expected_database)
                or url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "db"}
                or url.database != expected_database or settings.ai_provider != "mock" or settings.app_env != "test"
                or execute and confirmation != "SEED"):
            raise ValueError()
    except (TypeError, ValueError):
        raise SeedError("seed_target_refused") from None


async def run(args):
    settings = get_settings()
    validate_target(settings, args.expected_database, args.execute, args.confirm)
    as_of = instant(args.as_of)
    try:
        async with AsyncSessionLocal() as session, session.begin():
            result = await seed_fixture(session, as_of=as_of)
            if not args.execute:
                await session.rollback()
        return dict(result, mode="apply" if args.execute else "preview")
    finally:
        await close_db_connection()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guarded disposable synthetic fixture")
    parser.add_argument("--as-of", type=datetime.fromisoformat, required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (ValueError, SQLAlchemyError):
        print(json.dumps(dict(complete=False, code="seed_refused")))
        return 1
    print(json.dumps(dict(complete=True, **result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
