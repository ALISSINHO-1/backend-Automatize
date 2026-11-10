"""Non-destructive pg_dump/pg_restore exercise in the labeled audit container."""
import argparse
import json
import subprocess
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.infrastructure.database.data_api_security import (
    PROTECTED_TABLES, inspect_access, require_complete_visibility,
)
from scripts.isolated_database import require_isolated_database
from scripts.schema_preflight import capture_schema


def docker(*args):
    # Never echo driver errors, archive content, environment or credentials.
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Disposable container command failed")
    return result.stdout.strip()


def fingerprint(engine):
    with engine.connect() as c:
        c.exec_driver_sql("SET TRANSACTION READ ONLY")
        require_complete_visibility(c, PROTECTED_TABLES)
        tables = PROTECTED_TABLES
        # Hash all rows without exporting names, emails, password hashes or text.
        return {table: c.exec_driver_sql(
            f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY row_to_json(t)::text),'')) FROM public.{table} t"
        ).one() for table in tables}


def restore_schema(connection):
    schema = capture_schema(connection)
    # pg_dump/pg_restore on PG17 redistributes varchar->text array casts in
    # this published CHECK. Normalize only these two exact, equivalent forms;
    # unknown expressions (including wider channel sets) remain strict diffs.
    equivalent = {
        "canal::text = ANY (ARRAY['cliente'::character varying, 'interno'::character varying]::text[])",
        "canal::text = ANY (ARRAY['cliente'::character varying::text, 'interno'::character varying::text])",
    }
    for check in schema["tables"].get("chat_mensagens", {}).get("checks", []):
        if check["name"] == "chat_mensagens_canal_check" and check["sqltext"] in equivalent:
            check["sqltext"] = "canal IN ('cliente', 'interno')"
    return schema


def security_fingerprint(engine):
    with engine.connect() as c:
        c.exec_driver_sql("SET TRANSACTION READ ONLY")
        return {
            "access": inspect_access(c),
            "schema": restore_schema(c),
            "table_security": [tuple(row) for row in c.exec_driver_sql("""
                SELECT c.relname,pg_get_userbyid(c.relowner),c.relrowsecurity,c.relforcerowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname
            """)],
            "column_grants": [tuple(row) for row in c.exec_driver_sql("""
                SELECT c.relname,a.attname,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                CROSS JOIN LATERAL aclexplode(a.attacl) acl
                WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY c.relname,a.attname,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
            """)],
            "table_grants": [tuple(row) for row in c.exec_driver_sql("""
                SELECT c.relname,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
                WHERE n.nspname='public' AND c.relkind='r'
                ORDER BY c.relname,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
            """)],
            "default_grants": [tuple(row) for row in c.exec_driver_sql("""
                SELECT pg_get_userbyid(d.defaclrole),coalesce(n.nspname,'ALL_SCHEMAS'),
                    d.defaclobjtype,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
                FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
                CROSS JOIN LATERAL aclexplode(d.defaclacl) acl
                ORDER BY 1,2,3,4,5,6,7
            """)],
            "functions": [tuple(row) for row in c.exec_driver_sql("""
                SELECT p.proname,p.prosecdef,p.proconfig,pg_get_userbyid(p.proowner),
                    has_function_privilege('anon',p.oid,'EXECUTE'),
                    has_function_privilege('authenticated',p.oid,'EXECUTE')
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public' AND p.proname IN
                    ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log')
                ORDER BY p.proname
            """)],
            "policies": [tuple(row) for row in c.exec_driver_sql("""
                SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies
                WHERE schemaname='public' ORDER BY tablename,policyname
            """)],
        }


def validate(source_url, container, expected_label="2026-10-31"):
    from sqlalchemy.engine import make_url
    source = make_url(require_isolated_database(source_url))
    # Bind fingerprints to the exact Docker loopback endpoint, including when
    # localhost resolves to IPv6 or libpq query parameters override authority.
    if source.host not in {"localhost", "127.0.0.1"} or set(source.query) & {"host", "hostaddr", "port"}:
        raise ValueError("Unambiguous Docker loopback endpoint required")
    source = source.set(host="127.0.0.1")
    if docker("inspect", "--format", '{{index .Config.Labels "automatize.audit"}}', container) != expected_label:
        raise ValueError("An explicitly labeled disposable audit container is required")
    if docker("port", container, "5432/tcp") != f"127.0.0.1:{source.port}":
        raise ValueError("Local source does not match the disposable container")
    target_name = f"restore_{uuid4().hex}_test"
    archive = f"/tmp/{target_name}.dump"
    docker("exec", container, "pg_dump", "-U", "postgres", "-d", source.database, "--format=custom", f"--file={archive}")
    docker("exec", container, "createdb", "-U", "postgres", target_name)
    docker("exec", container, "pg_restore", "-U", "postgres", "-d", target_name,
           "--exit-on-error", archive)
    original = create_engine(source, hide_parameters=True)
    restored = create_engine(source.set(database=target_name), hide_parameters=True)
    try:
        if fingerprint(original) != fingerprint(restored):
            raise RuntimeError("Restore differs from source")
        if security_fingerprint(original) != security_fingerprint(restored):
            raise RuntimeError("Restore privileges, policies or function protection differ from source")
        with restored.connect() as c:
            revision = c.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one()
            enabled = c.exec_driver_sql("""
                SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
                WHERE n.nspname='public' AND t.tgenabled='O' AND NOT t.tgisinternal
                AND (c.relname,t.tgname,p.proname) IN (
                  ('aceites_formais','trg_aceites_formais_imutavel','bloquear_alteracao_aceite_formal'),
                  ('pedidos','trg_pedidos_protege_conclusao','proteger_conclusao_pedido'),
                  ('auditoria_logs','trg_auditoria_logs_imutavel','proteger_auditoria_log'))
            """).scalar_one()
            if enabled != 3:
                raise RuntimeError("Expected enabled trigger bindings required")
        return {"restored": True, "rows_and_fingerprints_equal": True, "security_equal": True,
                "triggers": 3, "revision": revision, "target": target_name,
                "roles_reused_in_same_cluster": True, "storage_bytes_restored": False}
    finally:
        original.dispose()
        restored.dispose()


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--audit-label", default="2026-10-31", help="Expected automatize.audit label on the disposable container.")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(os.environ.get("HML_DATABASE_URL", ""), args.container, args.audit_label)))
        return 0
    except Exception:
        print(json.dumps({"restored": False, "error": "Isolated restore validation unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
