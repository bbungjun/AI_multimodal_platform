"""Discover a single linear code revision without executing migrations/settings."""
import ast
from pathlib import Path
import re


def resolve_revision(directory: Path) -> str:
    """Reject malformed/disconnected lineage; never accept a DB-provided head."""
    try:
        parents = {}
        for path in sorted(directory.glob("*.py")):
            if path.name == "__init__.py":
                continue
            fields = {}
            for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                            if target.id in fields:
                                raise ValueError
                            fields[target.id] = ast.literal_eval(node.value)
            if set(fields) != {"revision", "down_revision"}:
                raise ValueError
            revision, parent = fields["revision"], fields["down_revision"]
            if (not isinstance(revision, str)
                    or re.fullmatch(r"[A-Za-z0-9_]{1,64}", revision) is None
                    or revision in parents
                    or (parent is not None and not isinstance(parent, str))):
                raise ValueError
            parents[revision] = parent
        if (not parents or sum(parent is None for parent in parents.values()) != 1
                or any(parent is not None and parent not in parents for parent in parents.values())):
            raise ValueError
        heads = set(parents) - set(parents.values())
        if len(heads) != 1:
            raise ValueError
        head = next(iter(heads))
        seen = set()
        current = head
        while current is not None:
            if current in seen:
                raise ValueError
            seen.add(current)
            current = parents[current]
        if seen != set(parents):
            raise ValueError
        return head
    except (OSError, SyntaxError, ValueError, TypeError, KeyError):
        raise ValueError("schema_lineage_invalid") from None


def load_code_revision(module_file: Path, workdir: Path) -> str:
    """Match source checkout and the packaged image's migration layout."""
    candidates = (module_file.resolve().parents[1] / "migrations" / "versions",
                  workdir / "migrations" / "versions")
    for directory in candidates:
        if directory.is_dir():
            # An invalid existing source is an error, not a reason to fall back.
            return resolve_revision(directory)
    raise ValueError("schema_lineage_invalid")


CODE_REVISION = load_code_revision(Path(__file__), Path.cwd())
