from hashlib import sha256
import json
from unittest.mock import Mock

import pytest

from scripts import schema_preflight as cli


def test_unapproved_reference_is_rejected_before_credentials_or_connection(tmp_path, monkeypatch):
    manifest = tmp_path / "reference.json"
    manifest.write_text(json.dumps({"format": 1}))
    settings, engine = Mock(), Mock()
    monkeypatch.setattr(cli, "Settings", settings)
    monkeypatch.setattr(cli, "create_database_engine", engine)
    assert cli.main(["--reference", str(manifest), "--reference-sha256", "wrong",
                     "--output", str(tmp_path/"new.json")]) == 2
    settings.assert_not_called()
    engine.assert_not_called()


def test_existing_evidence_is_never_overwritten(tmp_path, monkeypatch):
    evidence = tmp_path / "existing.json"
    evidence.write_text("preserve")
    settings = Mock()
    monkeypatch.setattr(cli, "Settings", settings)
    assert cli.main(["--export-reference", "--output", str(evidence)]) == 2
    assert evidence.read_text() == "preserve"
    settings.assert_not_called()


def test_reference_export_refuses_remote_configuration_before_connecting(tmp_path, monkeypatch, capsys):
    settings = Mock()
    settings.validate_database_configuration.return_value = "postgresql+psycopg2://remote.invalid/reference_test"
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    engine = Mock()
    monkeypatch.setattr(cli, "create_database_engine", engine)
    assert cli.main(["--export-reference", "--output", str(tmp_path/"reference.json")]) == 2
    engine.assert_not_called()
    assert "remote.invalid" not in capsys.readouterr().out


def test_reference_approval_is_for_exact_file_bytes(tmp_path):
    path = tmp_path / "reference.json"
    raw = b'{"format":1,"revision":"d8f4a2c6e901","server_major":17,"schema":{}}'
    path.write_bytes(raw)
    assert cli.load_reference(path, sha256(raw).hexdigest())["revision"] == "d8f4a2c6e901"
    path.write_bytes(raw+b"\n")
    with pytest.raises(ValueError, match="approval mismatch"):
        cli.load_reference(path, sha256(raw).hexdigest())
