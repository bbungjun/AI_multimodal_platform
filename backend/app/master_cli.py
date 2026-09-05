"""Local mock promotion CLI; default dry-run rolls back the simulated command."""
import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import AsyncSessionLocal, close_db_connection
from app.master_admin import MasterCommand, MasterError, REASONS, administer
from app.models import utc_now


def validate_target(settings, expected_database, user_id, execute, confirmation):
    try:
        url = make_url(settings.database_url)
        if (url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "db"}
                or not expected_database or url.database != expected_database
                or expected_database in {"postgres", "template0", "template1"}
                or settings.ai_provider != "mock" or settings.app_env not in {"local", "test"}
                or not isinstance(user_id, UUID)
                or (execute and confirmation != f"PROMOTE:{user_id}")):
            raise ValueError
    except (ValueError, TypeError):
        raise MasterError("master_cli_target_refused") from None


async def promote(args):
    settings = get_settings()
    validate_target(settings, args.expected_database, args.user_id, args.execute, args.confirm)
    command = MasterCommand(args.user_id, args.request_id, "promote", args.reason)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            receipt = await administer(session, actor_id=args.user_id, command=command,
                                       now=utc_now(), source="operator_cli")
            if not args.execute:
                await session.rollback()
    return {"action": "promote", "mode": "apply" if args.execute else "preview",
            "replayed": receipt.replayed, "role": receipt.after["role"], "plan": receipt.after["plan"]}


async def _run(args):
    try:
        return await promote(args)
    finally:
        await close_db_connection()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guarded local mock Master promotion")
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--request-id", type=UUID, required=True)
    parser.add_argument("--reason", choices=sorted(REASONS), required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except (MasterError, SQLAlchemyError):
        print(json.dumps({"complete": False, "code": "master_cli_refused"}))
        return 1
    print(json.dumps({"complete": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
