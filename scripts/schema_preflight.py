"""Read-only schema/data preflight against a reviewed isolated reference manifest.

Export is restricted to a local disposable database. Checking never migrates,
repairs, stamps or authorizes deployment. No application rows are exported.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.core.database import create_database_engine
from app.infrastructure.database.data_api_security import (
    PROTECTED_TABLES, assess_access, inspect_access, require_complete_visibility,
)
from scripts.isolated_database import require_isolated_database


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def capture_schema(connection):
    if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise ValueError("Read-only transaction required")
    connection.exec_driver_sql("SET LOCAL search_path=pg_catalog")
    inspector = inspect(connection)
    tables = {}
    for table in sorted(set(inspector.get_table_names(schema="public")) & set(PROTECTED_TABLES)):
        tables[table] = {
            "columns": [{"name": c["name"], "type": str(c["type"].compile(dialect=connection.dialect)), "nullable": c["nullable"],
                         "default": c["default"]} for c in inspector.get_columns(table, schema="public")],
            "pk": inspector.get_pk_constraint(table, schema="public"),
            "unique": inspector.get_unique_constraints(table, schema="public"),
            "checks": inspector.get_check_constraints(table, schema="public"),
            "foreign_keys": inspector.get_foreign_keys(table, schema="public"),
            "indexes": inspector.get_indexes(table, schema="public"),
        }
        for key in ("unique", "checks", "foreign_keys", "indexes"):
            tables[table][key].sort(key=lambda row: row.get("name") or "")
    # JSON round-trip makes SQLAlchemy tuples and PostgreSQL arrays portable.
    return json.loads(json.dumps({
        "tables": tables,
        "enums": sorted([e for e in inspector.get_enums(schema="public")
                         if e["name"] in ("enum_perfil", "enum_status", "enum_tipo_ocorrencia")],
                        key=lambda e: e["name"]),
        "functions": [dict(r) for r in connection.exec_driver_sql("""
            SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,
                p.prosecdef,p.proconfig,md5(pg_get_functiondef(p.oid)) AS definition_digest
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND p.proname IN
              ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log')
            ORDER BY p.proname,arguments
        """).mappings()],
        "triggers": [dict(r) for r in connection.exec_driver_sql("""
            SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid) AS definition
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal
            ORDER BY c.relname,t.tgname
        """).mappings() if r["relname"] in PROTECTED_TABLES],
    }, default=str))


def reference_manifest(connection):
    schema = capture_schema(connection)
    require_complete_visibility(connection, ("alembic_version",))
    revision = connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one()
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
    if scripts.get_revision(revision) is None:
        raise ValueError("Known migration revision required")
    return {"format": 1, "revision": revision, "server_major": int(connection.exec_driver_sql(
        "SHOW server_version_num").scalar_one()) // 10000, "schema": schema}


def preflight(connection, reference):
    if connection.in_transaction():
        raise ValueError("Fresh connection required")
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    actual = reference_manifest(connection)
    differences = [key for key in ("revision", "server_major") if actual[key] != reference[key]]
    for key in ("tables", "enums", "functions", "triggers"):
        if actual["schema"][key] != reference["schema"][key]:
            differences.append(key)
    tables = set(actual["schema"]["tables"])
    # Never report zero violations if the role cannot see every row.
    require_complete_visibility(connection, tuple(sorted(tables)))
    counts = {}
    queries = {
        "attachment_occurrence_mismatches": ({"anexos", "ocorrencias"},
            "SELECT count(*) FROM public.anexos a JOIN public.ocorrencias o ON o.id=a.ocorrencia_id WHERE a.pedido_id<>o.pedido_id"),
        "attachments_without_order": ({"anexos", "pedidos"},
            "SELECT count(*) FROM public.anexos a LEFT JOIN public.pedidos p ON p.id=a.pedido_id WHERE p.id IS NULL"),
        "attachments_without_sender": ({"anexos", "users"},
            "SELECT count(*) FROM public.anexos a LEFT JOIN public.users u ON u.id=a.enviado_por_id WHERE u.id IS NULL"),
        "attachments_without_occurrence": ({"anexos", "ocorrencias"},
            "SELECT count(*) FROM public.anexos a LEFT JOIN public.ocorrencias o ON o.id=a.ocorrencia_id WHERE a.ocorrencia_id IS NOT NULL AND o.id IS NULL"),
        "duplicate_acceptances": ({"aceites_formais"},
            "SELECT count(*) FROM (SELECT pedido_id FROM public.aceites_formais GROUP BY pedido_id HAVING count(*)>1) d"),
        "completed_without_acceptance": ({"pedidos", "aceites_formais"},
            "SELECT count(*) FROM public.pedidos p WHERE p.status='CONCLUIDO' AND NOT EXISTS (SELECT 1 FROM public.aceites_formais a WHERE a.pedido_id=p.id)"),
        "invalid_progress": ({"pedidos"},
            "SELECT count(*) FROM public.pedidos WHERE percentual_progresso<0 OR percentual_progresso>100"),
        "invalid_stage_completion": ({"etapas_operacionais"},
            "SELECT count(*) FROM public.etapas_operacionais WHERE NOT ((concluida AND concluida_em IS NOT NULL AND concluida_por_id IS NOT NULL) OR (NOT concluida AND concluida_em IS NULL AND concluida_por_id IS NULL))"),
        "invalid_homologation": ({"pedidos", "etapas_operacionais"},
            "SELECT count(*) FROM public.pedidos p WHERE p.status='HOMOLOGACAO' AND (NOT EXISTS (SELECT 1 FROM public.etapas_operacionais e WHERE e.pedido_id=p.id) OR EXISTS (SELECT 1 FROM public.etapas_operacionais e WHERE e.pedido_id=p.id AND NOT e.concluida))"),
    }
    for name, (required, sql) in queries.items():
        counts[name] = connection.exec_driver_sql(sql).scalar_one() if required <= tables else None
    access = inspect_access(connection)
    from dataclasses import asdict
    return {"readonly": True, "revision": actual["revision"], "reference_content_sha256": digest(reference),
            "schema_matches": not differences, "schema_differences": differences,
            "integrity_counts": counts, "access_findings": [asdict(f) for f in assess_access(access)],
            "technical_preflight_passed": not differences and all(v in (None, 0) for v in counts.values()),
            "deployment_authorized": False, "storage_validated": False,
            "manual_reviews": ["roles_and_inheritance", "default_privileges_per_creator", "storage_policies",
                               "backup_and_restore", "writers_drained", "operational_approval"]}


def load_reference(path, approved_sha256):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != approved_sha256:
        raise ValueError("Reference approval mismatch")
    reference = json.loads(raw)
    if reference.get("format") != 1 or not all(k in reference for k in ("revision", "server_major", "schema")):
        raise ValueError("Invalid reference")
    return reference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export-reference", action="store_true", help="Local disposable database only.")
    mode.add_argument("--reference", type=Path, help="Manifest captured from the same revision in isolation.")
    parser.add_argument("--reference-sha256", help="Human-reviewed SHA-256 of the exact manifest file bytes.")
    parser.add_argument("--output", type=Path, required=True, help="New restricted local evidence file; never overwrite.")
    args = parser.parse_args(argv)
    engine = None
    try:
        # Check approval and exclusive output before reading credentials/connecting.
        reference = load_reference(args.reference, args.reference_sha256) if args.reference else None
        with args.output.open("x", encoding="utf-8") as output:
            configured = Settings()
            if args.export_reference:
                require_isolated_database(configured.validate_database_configuration())
            engine = create_database_engine(configured, connect_args={"connect_timeout": 8,
                "options": "-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000"})
            with engine.connect() as connection:
                if args.export_reference:
                    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    result = reference_manifest(connection)
                else:
                    result = preflight(connection, reference)
                    result["reference_file_sha256"] = args.reference_sha256
            output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"evidence_written": True, "deployment_authorized": False,
                          "technical_preflight_passed": result.get("technical_preflight_passed")}))
        return 0 if args.export_reference or result["technical_preflight_passed"] else 1
    except Exception:
        print(json.dumps({"preflight_unavailable": True, "deployment_authorized": False}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
