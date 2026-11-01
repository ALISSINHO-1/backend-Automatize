"""Non-destructive pg_dump/pg_restore exercise in the labeled audit container."""
import argparse
import json
import subprocess
from uuid import uuid4

from sqlalchemy import create_engine, text

from scripts.isolated_database import require_isolated_database


def docker(*args):
    # Never echo driver errors, archive content, environment or credentials.
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Disposable container command failed")
    return result.stdout.strip()


def fingerprint(engine):
    with engine.connect() as c:
        c.exec_driver_sql("SET TRANSACTION READ ONLY")
        tables = ("users", "pedidos", "ocorrencias", "etapas_operacionais", "aceites_formais", "auditoria_logs", "anexos", "historico_status_pedidos", "alembic_version")
        # Hash all rows without exporting names, emails, password hashes or text.
        return {table: c.exec_driver_sql(
            f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY row_to_json(t)::text),'')) FROM public.{table} t"
        ).one() for table in tables}


def validate(source_url, container):
    from sqlalchemy.engine import make_url
    source = make_url(require_isolated_database(source_url))
    if docker("inspect", "--format", '{{index .Config.Labels "automatize.audit"}}', container) != "2026-10-31":
        raise ValueError("An explicitly labeled disposable audit container is required")
    if docker("port", container, "5432/tcp") != f"127.0.0.1:{source.port}":
        raise ValueError("Local source does not match the disposable container")
    target_name = f"restore_{uuid4().hex}_test"
    archive = f"/tmp/{target_name}.dump"
    docker("exec", container, "pg_dump", "-U", "postgres", "-d", source.database, "--format=custom", f"--file={archive}")
    docker("exec", container, "createdb", "-U", "postgres", target_name)
    docker("exec", container, "pg_restore", "-U", "postgres", "-d", target_name,
           "--no-owner", "--no-privileges", "--exit-on-error", archive)
    original = create_engine(source, hide_parameters=True)
    restored = create_engine(source.set(database=target_name), hide_parameters=True)
    try:
        if fingerprint(original) != fingerprint(restored):
            raise RuntimeError("Restore differs from source")
        with restored.connect() as c:
            revision = c.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one()
            assert c.exec_driver_sql("SELECT count(*) FROM pg_trigger WHERE tgname IN ('trg_aceites_formais_imutavel','trg_pedidos_protege_conclusao','trg_auditoria_logs_imutavel')").scalar_one() == 3
        return {"restored": True, "rows_and_fingerprints_equal": True,
                "triggers": 3, "revision": revision, "target": target_name}
    finally:
        original.dispose()
        restored.dispose()


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(os.environ.get("HML_DATABASE_URL", ""), args.container)))
        return 0
    except Exception:
        print(json.dumps({"restored": False, "error": "Isolated restore validation unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
