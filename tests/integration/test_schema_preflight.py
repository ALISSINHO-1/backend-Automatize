"""No shared connection: every schema mutation uses a guarded scratch database."""
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from scripts.schema_preflight import preflight, reference_manifest
from app.infrastructure.database.data_api_security import IncompleteVisibilityError
from tests.integration.test_migration_upgrade import fresh_database, upgrade


def reference(engine):
    with engine.connect() as c:
        c.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return reference_manifest(c)


@pytest.fixture
def scratch(engine, monkeypatch):
    database = fresh_database(engine)
    upgrade(database, monkeypatch)
    yield database
    database.dispose()


def test_clean_preflight_is_readonly_and_never_authorizes_deployment(scratch):
    expected = reference(scratch)
    perfil = next(c for c in expected["schema"]["tables"]["users"]["columns"] if c["name"] == "perfil")
    assert "enum_perfil" in perfil["type"]
    with scratch.connect() as c:
        report = preflight(c, expected)
        assert report["technical_preflight_passed"]
        assert report["deployment_authorized"] is False
        assert report["storage_validated"] is False
        assert set(report["integrity_counts"].values()) == {0}
        with pytest.raises(DBAPIError) as exc:
            c.exec_driver_sql("UPDATE public.users SET nome=nome WHERE false")
        assert exc.value.orig.pgcode == "25006"


@pytest.mark.parametrize("change,section", [
    ("ALTER TABLE public.anexos ADD COLUMN unexpected text", "tables"),
    ("ALTER TABLE public.pedidos DISABLE TRIGGER trg_pedidos_protege_conclusao", "triggers"),
    ("CREATE OR REPLACE FUNCTION public.proteger_conclusao_pedido() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $$ BEGIN RETURN NEW; END; $$", "functions"),
])
def test_same_revision_does_not_hide_catalog_drift(scratch, change, section):
    expected = reference(scratch)
    with scratch.begin() as c:
        c.exec_driver_sql(change)
    with scratch.connect() as c:
        report = preflight(c, expected)
    assert report["revision"] == expected["revision"]
    assert section in report["schema_differences"]
    assert report["technical_preflight_passed"] is False


def test_metadata_only_old_baseline_is_not_equivalent_to_rewritten_initial(engine, monkeypatch):
    expected_db, old_baseline = fresh_database(engine), fresh_database(engine)
    try:
        upgrade(expected_db, monkeypatch, "a4fa37701385")
        expected = reference(expected_db)
        # Reproduce main's historical no-DDL baseline, not a stamp workaround.
        with old_baseline.begin() as c:
            c.exec_driver_sql("CREATE TABLE public.alembic_version(version_num varchar(32) PRIMARY KEY)")
            c.exec_driver_sql("INSERT INTO public.alembic_version VALUES ('a4fa37701385')")
        with old_baseline.connect() as c:
            report = preflight(c, expected)
        assert report["revision"] == expected["revision"]
        assert "tables" in report["schema_differences"]
        assert report["technical_preflight_passed"] is False
    finally:
        expected_db.dispose()
        old_baseline.dispose()


def test_legacy_cross_order_attachment_blocks_preflight(engine, monkeypatch):
    database = fresh_database(engine)
    try:
        upgrade(database, monkeypatch, "3c9e7a1b5d20")
        expected = reference(database)
        with database.begin() as c:
            user = c.exec_driver_sql("INSERT INTO public.users(nome,email,senha_hash) VALUES ('Synthetic','preflight@test.invalid','unused') RETURNING id").scalar_one()
            ids = [c.exec_driver_sql("INSERT INTO public.pedidos(codigo_identificador,titulo,cliente_id) VALUES (%s,'Synthetic',%s) RETURNING id", (str(uuid4()), user)).scalar_one() for _ in range(2)]
            occurrence = c.exec_driver_sql("INSERT INTO public.ocorrencias(pedido_id,autor_id,tipo,descricao) VALUES (%s,%s,'ERRO','Synthetic') RETURNING id", (ids[0], user)).scalar_one()
            c.exec_driver_sql("INSERT INTO public.anexos(pedido_id,ocorrencia_id,enviado_por_id,nome_arquivo,caminho_storage,extensao,tamanho_bytes) VALUES (%s,%s,%s,'synthetic.pdf','synthetic','pdf',1)", (ids[1], occurrence, user))
        with database.connect() as c:
            report = preflight(c, expected)
        assert report["schema_matches"] is True
        assert report["integrity_counts"]["attachment_occurrence_mismatches"] == 1
        assert report["technical_preflight_passed"] is False
    finally:
        database.dispose()


def test_rls_filtered_visibility_cannot_report_empty_data_as_clean(scratch):
    expected = reference(scratch)
    with scratch.begin() as c:
        c.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon")
        c.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon")
    with scratch.connect() as c:
        c.exec_driver_sql("SET ROLE anon")
        c.commit()
        try:
            with pytest.raises(IncompleteVisibilityError):
                preflight(c, expected)
        finally:
            c.rollback()
            c.exec_driver_sql("RESET ROLE")
            c.commit()


def test_fresh_connection_is_required_for_consistent_snapshot(scratch):
    expected = reference(scratch)
    with scratch.connect() as c:
        c.exec_driver_sql("SELECT 1")
        with pytest.raises(ValueError, match="Fresh connection"):
            preflight(c, expected)


def test_unknown_revision_is_refused_instead_of_trusting_the_label(scratch):
    expected = reference(scratch)
    with scratch.begin() as c:
        c.exec_driver_sql("UPDATE public.alembic_version SET version_num='unknown_test'")
    from alembic.script.revision import ResolutionError
    from alembic.util.exc import CommandError
    with scratch.connect() as c, pytest.raises((ResolutionError, CommandError)):
        preflight(c, expected)
