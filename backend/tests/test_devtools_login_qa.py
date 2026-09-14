from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import devtools_login_qa


def test_cli_rejects_external_targets_before_startup(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devtools_login_qa.py", "https://example.test"])
    assert devtools_login_qa.main() == 2
    assert "arguments_refused" in capsys.readouterr().out


def test_source_digest_changes_with_runtime_source(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("original", encoding="utf-8")
    monkeypatch.setattr(devtools_login_qa, "ROOT", tmp_path)
    monkeypatch.setattr(devtools_login_qa.subprocess, "check_output", lambda *a, **kw: b"app.py\0")
    before = devtools_login_qa.source_digest()
    (tmp_path / "app.py").write_text("changed", encoding="utf-8")
    assert devtools_login_qa.source_digest() != before


def test_refusal_delta_excludes_one_allowed_generation():
    before = {"complete": True, "jobs": 0, "outbox": 0, "reservations": 0}
    refused = {"complete": True, "jobs": 1, "outbox": 1, "reservations": 4}
    admitted = {"complete": True, "jobs": 2, "outbox": 2, "reservations": 5}

    assert devtools_login_qa.refusal_deltas(before, refused) == {
        "jobs": 0, "outbox": 0, "reservations": 0
    }
    assert devtools_login_qa.refusal_deltas(before, admitted) == {
        "jobs": 1, "outbox": 1, "reservations": 1
    }
