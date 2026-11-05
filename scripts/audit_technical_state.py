"""Read-only catalog evidence; never exports application rows or credentials."""
from dataclasses import asdict
import argparse
import json

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import create_database_engine
from app.infrastructure.database.data_api_security import assess_access, inspect_access


def inspect_catalog(connection, bucket):
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise RuntimeError("Read-only transaction required")
    result = {
        "readonly": True,
        "server": connection.exec_driver_sql("SHOW server_version").scalar_one(),
        "revision": connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalars().all(),
    }
    result["backend_role"] = dict(connection.exec_driver_sql(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
        "FROM pg_roles WHERE rolname=current_user"
    ).mappings().one())
    result["access"] = inspect_access(connection)
    result["findings"] = [asdict(f) for f in assess_access(result["access"])]
    result["functions"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT p.proname, p.prosecdef, p.proconfig,
            pg_get_userbyid(p.proowner)=current_user AS owned_by_backend,
            has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
            has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname IN
            ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log')
    """).mappings()]
    result["triggers"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT c.relname AS table_name,t.tgname,t.tgenabled,p.proname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE n.nspname='public' AND NOT t.tgisinternal
            AND c.relname IN ('aceites_formais','auditoria_logs','pedidos')
        ORDER BY c.relname,t.tgname
    """).mappings()]
    result["public_grants"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT n.nspname AS schema_name,c.relname AS table_name,a.privilege_type
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE a.grantee=0 AND c.relkind='r' AND (
            (n.nspname='public' AND c.relname IN
                ('users','pedidos','ocorrencias','anexos','aceites_formais','auditoria_logs',
                 'historico_status_pedidos','etapas_operacionais','alembic_version'))
            OR (n.nspname='storage' AND c.relname IN ('objects','buckets')))
        ORDER BY n.nspname,c.relname,a.privilege_type
    """).mappings()]
    result["public_column_grants"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT c.relname AS table_name,col.attname AS column_name,a.privilege_type
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute col ON col.attrelid=c.oid
        CROSS JOIN LATERAL aclexplode(col.attacl) a
        WHERE n.nspname='public' AND col.attnum>0 AND NOT col.attisdropped AND a.grantee=0
            AND c.relname IN ('users','pedidos','ocorrencias','anexos','aceites_formais',
                'auditoria_logs','historico_status_pedidos','etapas_operacionais','alembic_version')
        ORDER BY c.relname,col.attname,a.privilege_type
    """).mappings()]
    result["role_boundaries"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT CASE WHEN r.rolname=current_user THEN 'backend' ELSE r.rolname END AS role_name,
            r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolcanlogin,r.rolinherit,
            has_schema_privilege(r.oid,'public','CREATE') AS public_schema_create,
            has_database_privilege(r.oid,current_database(),'CREATE') AS database_create,
            pg_has_role(r.rolname,current_user,'MEMBER') AS member_of_backend
        FROM pg_roles r
        WHERE r.rolname IN ('anon','authenticated','service_role','postgres',current_user)
        ORDER BY role_name
    """).mappings()]
    result["public_schema_create_granted"] = connection.exec_driver_sql("""
        SELECT EXISTS(SELECT 1 FROM pg_namespace n,
            LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
            WHERE n.nspname='public' AND a.grantee=0 AND a.privilege_type='CREATE')
    """).scalar_one()
    result["default_grants"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT coalesce(n.nspname,'ALL_SCHEMAS') AS schema_name,
            d.defaclrole=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS creator_is_backend,
            d.defaclobjtype AS object_type,
            CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE r.rolname END AS grantee,
            a.privilege_type
        FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
        CROSS JOIN LATERAL aclexplode(d.defaclacl) a LEFT JOIN pg_roles r ON r.oid=a.grantee
        WHERE (d.defaclnamespace=0 OR n.nspname IN ('public','storage'))
            AND (a.grantee=0 OR r.rolname IN ('anon','authenticated','service_role'))
        ORDER BY schema_name,object_type,grantee,a.privilege_type
    """).mappings()]
    result["policies"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT schemaname,tablename,policyname,roles,cmd,permissive,qual,with_check FROM pg_policies
        WHERE schemaname IN ('public','storage') ORDER BY schemaname,tablename,policyname
    """).mappings()]
    result["storage_available"] = connection.exec_driver_sql(
        "SELECT to_regclass('storage.buckets') IS NOT NULL AND to_regclass('storage.objects') IS NOT NULL"
    ).scalar_one()
    result["bucket"] = []
    if result["storage_available"]:
        result["bucket"] = [dict(r) for r in connection.execute(text(
            "SELECT public,file_size_limit,allowed_mime_types FROM storage.buckets WHERE id=:bucket"
        ), {"bucket": bucket}).mappings()]
    result["storage_rls"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='storage' AND c.relname IN ('objects','buckets')
    """).mappings()]
    result["storage_grants"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT c.relname AS table_name,
            CASE WHEN r.rolname=current_user THEN 'backend' ELSE r.rolname END AS role_name,
            has_table_privilege(r.oid,c.oid,'SELECT') AS select,
            has_table_privilege(r.oid,c.oid,'INSERT') AS insert,
            has_table_privilege(r.oid,c.oid,'UPDATE') AS update,
            has_table_privilege(r.oid,c.oid,'DELETE') AS delete,
            has_table_privilege(r.oid,c.oid,'TRUNCATE') AS truncate
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN pg_roles r
        WHERE n.nspname='storage' AND c.relname IN ('buckets','objects')
            AND r.rolname IN ('anon','authenticated','service_role',current_user)
        ORDER BY c.relname,role_name
    """).mappings()]
    result["integrity_counts"] = dict(connection.exec_driver_sql("""
        SELECT
            (SELECT count(*) FROM public.anexos a JOIN public.ocorrencias o ON o.id=a.ocorrencia_id
                WHERE a.pedido_id<>o.pedido_id) AS attachment_occurrence_mismatches,
            (SELECT count(*) FROM public.pedidos p WHERE p.status='CONCLUIDO' AND NOT EXISTS
                (SELECT 1 FROM public.aceites_formais a WHERE a.pedido_id=p.id)) AS completed_without_acceptance,
            (SELECT count(*) FROM (SELECT pedido_id FROM public.aceites_formais GROUP BY pedido_id HAVING count(*)>1) d) AS duplicate_acceptances
    """).mappings().one())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-probe", action="store_true", help="Read bucket metadata with the configured SDK.")
    args = parser.parse_args()
    engine = None
    try:
        settings = Settings()
        engine = create_database_engine(settings, connect_args={
            "connect_timeout": 8,
            "options": "-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000",
        })
        with engine.connect() as connection:
            result = inspect_catalog(connection, settings.STORAGE_BUCKET_NAME)
        if args.storage_probe:
            try:
                from app.infrastructure.storage.supabase_storage import create_supabase_client
                metadata = create_supabase_client(settings).storage.get_bucket(settings.STORAGE_BUCKET_NAME)
                result["storage_sdk"] = {"reachable": True, "bucket_private": not metadata.public}
            except Exception:
                result["storage_sdk"] = {"reachable": False}
        print(json.dumps(result, default=str, ensure_ascii=False))
        return 0
    except Exception as exc:
        # No exception message: a driver or Settings error may contain secrets.
        print(json.dumps({"audit_unavailable": type(exc).__name__}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
