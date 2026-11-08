from unittest.mock import MagicMock, Mock

import pytest

from scripts import validate_hml_restore as restore


@pytest.mark.parametrize("authority", [
    "localhost:55427/restore_test?host=localhost",
    "localhost:55427/restore_test?hostaddr=127.0.0.1",
    "localhost:55427/restore_test?port=55428",
    "[::1]:55427/restore_test",
])
def test_restore_refuses_ambiguous_endpoint_before_docker(authority, monkeypatch):
    docker = Mock()
    monkeypatch.setattr(restore, "docker", docker)
    with pytest.raises(ValueError):
        restore.validate("postgresql+psycopg2://"+authority, "synthetic-container")
    docker.assert_not_called()


@pytest.mark.parametrize("failure", ["rows", "security", "disabled-trigger"])
def test_restore_cannot_report_success_after_partial_failure(failure, monkeypatch):
    calls = []
    def docker(*args):
        calls.append(args)
        return "synthetic-label" if args[0] == "inspect" else "127.0.0.1:55427" if args[0] == "port" else ""
    monkeypatch.setattr(restore, "docker", docker)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.exec_driver_sql.return_value.scalar_one.side_effect = ["d8f4a2c6e901", 0]
    monkeypatch.setattr(restore, "create_engine", lambda *a, **k: engine)
    rows = Mock(side_effect=[{"row":1},{"row":2}] if failure == "rows" else [{"row":1}]*2)
    security = Mock(side_effect=[{"acl":1},{"acl":2}] if failure == "security" else [{"acl":1}]*2)
    monkeypatch.setattr(restore, "fingerprint", rows)
    monkeypatch.setattr(restore, "security_fingerprint", security)
    with pytest.raises(RuntimeError):
        restore.validate("postgresql+psycopg2://localhost:55427/restore_test", "synthetic-container", "synthetic-label")
    command = next(c for c in calls if "pg_restore" in c)
    assert not {"--clean", "--no-owner", "--no-privileges"} & set(command)
    assert engine.dispose.call_count == 2
