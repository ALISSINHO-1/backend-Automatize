from unittest.mock import MagicMock

import pytest

from scripts import validate_hml_restore as restore


def test_restore_refuses_an_unlabeled_container_before_dump(monkeypatch):
    docker = MagicMock(return_value="wrong-label")
    monkeypatch.setattr(restore, "docker", docker)
    with pytest.raises(ValueError, match="labeled"):
        restore.validate("postgresql+psycopg2://localhost:55427/restore_test", "synthetic-container")
    assert docker.call_count == 1


def test_restore_preserves_privileges_and_checks_security(monkeypatch):
    calls = []
    def docker(*args):
        calls.append(args)
        return "2026-11-02" if args[0] == "inspect" else "127.0.0.1:55427" if args[0] == "port" else ""
    monkeypatch.setattr(restore, "docker", docker)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.exec_driver_sql.return_value.scalar_one.side_effect = ["d8f4a2c6e901", 3]
    monkeypatch.setattr(restore, "create_engine", lambda *a, **k: engine)
    monkeypatch.setattr(restore, "fingerprint", lambda e: {"synthetic": (1, "same")})
    security = MagicMock(return_value={"same": True})
    monkeypatch.setattr(restore, "security_fingerprint", security)
    result = restore.validate("postgresql+psycopg2://localhost:55427/restore_test", "synthetic-container", "2026-11-02")
    assert result["security_equal"] is True
    assert security.call_count == 2
    command = next(c for c in calls if "pg_restore" in c)
    assert "--no-privileges" not in command and "--clean" not in command


def test_restore_equates_only_pg17_chat_array_cast_forms(monkeypatch):
    from copy import deepcopy
    forms = [
        "canal::text = ANY (ARRAY['cliente'::character varying, 'interno'::character varying]::text[])",
        "canal::text = ANY (ARRAY['cliente'::character varying::text, 'interno'::character varying::text])",
    ]
    results = []
    for expression in forms:
        schema = {"tables": {"chat_mensagens": {"checks": [{"name": "chat_mensagens_canal_check", "sqltext": expression}]}}}
        monkeypatch.setattr(restore, "capture_schema", lambda c: deepcopy(schema))
        results.append(restore.restore_schema(None))
    assert results[0] == results[1]


@pytest.mark.parametrize("expression", ["true", "canal IN ('cliente','interno','publico')"])
def test_restore_does_not_hide_weaker_channel_constraints(monkeypatch, expression):
    schema = {"tables": {"chat_mensagens": {"checks": [{"name": "chat_mensagens_canal_check", "sqltext": expression}]}}}
    monkeypatch.setattr(restore, "capture_schema", lambda c: schema)
    assert restore.restore_schema(None)["tables"]["chat_mensagens"]["checks"][0]["sqltext"] == expression
