from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db_schema() -> None:
    # Import models here so metadata is populated before create_all runs.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_jobs_retry_of_schema)


def _sync_jobs_retry_of_schema(conn) -> None:
    inspector = inspect(conn)
    table_names = set(inspector.get_table_names())
    if "jobs" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "retry_of_job_id" not in columns:
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE jobs ADD COLUMN retry_of_job_id UUID"))
        else:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN retry_of_job_id CHAR(32)"))

    indexes = {index["name"] for index in inspector.get_indexes("jobs")}
    if "ix_jobs_retry_of_job_id" not in indexes:
        conn.execute(
            text("CREATE INDEX ix_jobs_retry_of_job_id ON jobs (retry_of_job_id)")
        )

    if conn.dialect.name != "postgresql":
        return

    foreign_keys = inspector.get_foreign_keys("jobs")
    has_retry_fk = any(
        foreign_key.get("name") == "fk_jobs_retry_of_job_id_jobs"
        or foreign_key.get("constrained_columns") == ["retry_of_job_id"]
        for foreign_key in foreign_keys
    )
    if not has_retry_fk:
        conn.execute(
            text(
                "ALTER TABLE jobs "
                "ADD CONSTRAINT fk_jobs_retry_of_job_id_jobs "
                "FOREIGN KEY (retry_of_job_id) REFERENCES jobs(id) "
                "ON DELETE SET NULL"
            )
        )


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db_connection() -> None:
    await engine.dispose()
