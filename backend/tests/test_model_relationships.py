from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy.dialects import postgresql

from app.models import ACTIVE_I2V_INDEX_STATES, Asset, Job, PromptEnhancement
from app.services.jobs import i2v_guard


def _single_foreign_key(column: Column):
    assert len(column.foreign_keys) == 1
    return next(iter(column.foreign_keys))


def test_job_optional_foreign_keys_detach_on_parent_deletion():
    expected = [
        (Job.__table__.c.enhancement_id, "prompt_enhancements.id"),
        (Job.__table__.c.parent_job_id, "jobs.id"),
        (Job.__table__.c.retry_of_job_id, "jobs.id"),
        (Job.__table__.c.source_asset_id, "assets.id"),
    ]

    for column, target in expected:
        foreign_key = _single_foreign_key(column)

        assert str(foreign_key.column) == target
        assert foreign_key.ondelete == "SET NULL"
        assert column.nullable is True


def test_job_retry_of_job_id_has_lookup_index():
    column = Job.__table__.c.retry_of_job_id

    assert any(column.name in index.columns for index in Job.__table__.indexes)


def test_job_has_active_i2v_source_asset_partial_unique_index():
    index = next(
        index
        for index in Job.__table__.indexes
        if index.name == "uq_jobs_active_i2v_source_asset"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["source_asset_id"]
    where = str(
        index.dialect_options["postgresql"]["where"].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "jobs.mode = 'i2v'" in where
    assert "jobs.source_asset_id is not null" in where
    assert "jobs.state in" in where
    assert "'polling'" in where
    assert "'completed'" not in where


def test_job_active_i2v_index_states_match_guard_states():
    assert ACTIVE_I2V_INDEX_STATES == i2v_guard.ACTIVE_I2V_STATES


def test_asset_job_foreign_key_cascades_with_owned_job():
    column = Asset.__table__.c.job_id
    foreign_key = _single_foreign_key(column)

    assert str(foreign_key.column) == "jobs.id"
    assert foreign_key.ondelete == "CASCADE"
    assert column.nullable is False


def test_job_assets_relationship_owns_generated_asset_rows():
    relationship = Job.__mapper__.relationships["assets"]

    assert relationship.mapper.class_ is Asset
    assert relationship.back_populates == "job"
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade


def test_prompt_enhancement_relationship_is_optional_job_link():
    relationship = Job.__mapper__.relationships["enhancement"]
    reverse_relationship = PromptEnhancement.__mapper__.relationships["jobs"]

    assert relationship.mapper.class_ is PromptEnhancement
    assert relationship.back_populates == "jobs"
    assert reverse_relationship.mapper.class_ is Job
    assert reverse_relationship.back_populates == "enhancement"
