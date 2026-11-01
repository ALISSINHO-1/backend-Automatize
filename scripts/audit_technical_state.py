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
            ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido')
    """).mappings()]
    result["policies"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT schemaname,tablename,policyname,roles,cmd,permissive FROM pg_policies
        WHERE schemaname IN ('public','storage') ORDER BY schemaname,tablename,policyname
    """).mappings()]
    result["bucket"] = [dict(r) for r in connection.execute(text(
        "SELECT public,file_size_limit,allowed_mime_types FROM storage.buckets WHERE id=:bucket"
    ), {"bucket": bucket}).mappings()]
    result["storage_rls"] = [dict(r) for r in connection.exec_driver_sql("""
        SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='storage' AND c.relname IN ('objects','buckets')
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
        engine = create_database_engine(settings, connect_args={"connect_timeout": 8})
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
