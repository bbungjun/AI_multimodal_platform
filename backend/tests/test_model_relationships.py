from __future__ import annotations

from sqlalchemy import Column

from app.models import Asset, Job, PromptEnhancement


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
