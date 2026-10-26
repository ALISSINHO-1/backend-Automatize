from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
import pytest

from app.core.config import Settings, validate_database_url
from app.core.database import create_database_engine
from app.core.postgres_tls import parameters_from_url, secure_connect_parameters


@pytest.fixture(autouse=True)
def isolate_libpq_environment(monkeypatch):
    for key in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGSSLMODE"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("url", [
    "postgresql://fixture:fixture@remote.example/db",
    "postgresql://fixture:fixture@remote.example/db?sslmode=require",
    "postgresql://fixture:fixture@remote.example/db?sslmode=verify-full&sslrootcert=ca.pem",
    "postgresql+psycopg2://fixture:fixture@pooler.supabase.com:6543/db?sslmode=require",
    "postgresql:///db?host=remote.example",
    "postgresql://fixture:fixture@localhost/db?host=remote.example",
    "postgresql://fixture:fixture@localhost/db?hostaddr=203.0.113.10",
    "postgresql:///db?host=localhost,remote.example",
    "postgresql:///db?host=localhost:5432&host=remote.example:5432",
])
def test_remote_effective_targets_always_require_tls(url):
    checked = make_url(validate_database_url(url))
    params = parameters_from_url(checked)
    assert params["sslmode"] in {"require", "verify-ca", "verify-full"}
    assert params["gssencmode"] == "disable"


@pytest.mark.parametrize("query", [
    "sslmode=disable", "sslmode=prefer", "sslmode=allow",
    "host=remote.example&sslmode=disable", "hostaddr=203.0.113.10&sslmode=disable",
    "host=localhost,remote.example&sslmode=disable",
    "sslmode=require&sslmode=disable", "sslmode=disable&sslmode=require",
    "sslmode=require&requiressl=0", "sslmode=require&ssl=false",
    "sslmode=require&service=unreviewed", "sslmode=require&dsn=sslmode%3Ddisable",
    "sslmode=require&dbname=postgresql%3A%2F%2Fremote.example%2Fdb",
    "sslmode=require&gssencmode=require",
])
def test_remote_insecure_and_conflicting_parameters_are_rejected_without_secrets(query):
    url = "postgresql://private-user:private-password@remote.example/db?" + query
    with pytest.raises(ValueError) as error:
        validate_database_url(url)
    assert "private-user" not in str(error.value)
    assert "private-password" not in str(error.value)
    assert "remote.example" not in str(error.value)


@pytest.mark.parametrize("url", [
    "postgresql://fixture:fixture@localhost/db?host=remote.example&sslmode=disable",
    "postgresql:///db?host=remote.example&sslmode=disable",
    "postgresql://fixture:fixture@localhost/db?hostaddr=203.0.113.10&sslmode=disable",
])
def test_audit_bypasses_are_closed(url):
    with pytest.raises(ValueError):
        validate_database_url(url)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "[::1]"])
def test_local_disposable_postgresql_can_explicitly_disable_tls(host):
    checked = validate_database_url(f"postgresql://fixture:fixture@{host}/db?sslmode=disable")
    assert make_url(checked).query["sslmode"] == "disable"


def test_sqlite_test_engines_are_unaffected():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("overrides", [
    {"sslmode": "disable"},
    {"hostaddr": "203.0.113.10", "sslmode": "disable"},
    {"dsn": "host=remote.example sslmode=disable"},
    {"service": "unreviewed"},
    {"dbname": "host=remote.example sslmode=disable"},
    {"sslmode": ("require", "disable")},
])
def test_connect_args_cannot_override_remote_tls(overrides):
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://fixture:fixture@remote.example/db")
    with pytest.raises(ValueError):
        create_database_engine(settings, connect_args=overrides)


def test_effective_local_url_with_remote_connect_args_is_rejected():
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://fixture:fixture@localhost/db?sslmode=disable")
    with pytest.raises(ValueError):
        create_database_engine(settings, connect_args={"host": "remote.example"})


def test_final_driver_parameters_are_checked_before_network(monkeypatch):
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://fixture:fixture@remote.example/db")
    engine = create_database_engine(settings)
    called = []
    monkeypatch.setattr(engine.dialect.loaded_dbapi, "connect", lambda *args, **kwargs: called.append(True))
    try:
        with pytest.raises(ValueError):
            engine.dialect.dispatch.do_connect(engine.dialect, None, [], {"host": "remote.example", "sslmode": "disable"})
        assert called == []
    finally:
        engine.dispose()


def test_local_factory_options_remain_available_without_connection():
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://fixture:fixture@localhost/db")
    engine = create_database_engine(settings, connect_args={"sslmode": "disable", "connect_timeout": 3})
    engine.dispose()


@pytest.mark.parametrize("variable,value", [
    ("PGHOSTADDR", "203.0.113.10"), ("PGSERVICE", "unreviewed"),
])
def test_environment_cannot_turn_local_exception_into_remote_plaintext(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        validate_database_url("postgresql://fixture:fixture@localhost/db?sslmode=disable")


def test_remote_url_overrides_insecure_libpq_environment(monkeypatch):
    monkeypatch.setenv("PGSSLMODE", "disable")
    checked = validate_database_url("postgresql:///db")
    assert make_url(checked).query["sslmode"] == "require"


def test_opaque_nested_database_dsn_is_rejected():
    with pytest.raises(ValueError):
        secure_connect_parameters({"host": "localhost", "dbname": "postgresql://remote.example/db?sslmode=disable"})
