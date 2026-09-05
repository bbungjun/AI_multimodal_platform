"""Code revision discovery never executes migration Python or application config."""
from pathlib import Path

import pytest

from app.schema_revision import CODE_REVISION, resolve_revision


def graph(tmp_path, pairs):
    for index, (revision, parent) in enumerate(pairs):
        (tmp_path / f"migration_{index}.py").write_text(
            f"revision = {revision!r}\ndown_revision = {parent!r}\n"
            "raise RuntimeError('must not execute')\n", encoding="utf-8")
    return tmp_path


def test_current_head_and_read_only_literal_graph(tmp_path):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    assert ScriptDirectory.from_config(config).get_current_head() == CODE_REVISION
    assert resolve_revision(graph(tmp_path, [("a", None), ("b", "a")])) == "b"


@pytest.mark.parametrize("pairs", [[], [("a", "missing")],
    [("a", None), ("b", None)], [("a", None), ("b", "a"), ("c", "a")],
    [("a", "b"), ("b", "a")], [("a", None), ("a", None)],
    [("a", None), ("b", "c"), ("c", "b")], [("bad name", None)],
    [("a", None), ("b", ("a",))]])
def test_invalid_lineage_fails_closed(tmp_path, pairs):
    with pytest.raises(ValueError, match="schema_lineage_invalid"):
        resolve_revision(graph(tmp_path, pairs))


@pytest.mark.parametrize("source", ["revision = call()\ndown_revision = None",
    "revision = 'a'", "revision = 'a'\nrevision = 'b'\ndown_revision = None",
    "not python !"])
def test_nonliteral_missing_duplicate_metadata_rejected(tmp_path, source):
    (tmp_path / "bad.py").write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="schema_lineage_invalid"):
        resolve_revision(tmp_path)
