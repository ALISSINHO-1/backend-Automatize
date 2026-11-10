"""Rehearse a synthetic legacy snapshot upgrade in a labeled local container.

Never reads shared Supabase or treats synthetic ACLs as production equivalence.
Requires TEST_DATABASE_URL and the exact Docker loopback/label checks below.
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.domain.models import ChatMensagem, MovimentoQuadro, User
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.infrastructure.database.data_api_security import PROTECTED_TABLES, assess_access, inspect_access
from app.services.demand_service import DemandService
from scripts.isolated_database import require_isolated_database
from scripts.validate_hml_restore import docker, fingerprint, security_fingerprint, validate


def migrate(engine, revision):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
    try:
        command.upgrade(config, revision)
        if revision == "head":
            command.check(config)
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original


def legacy_rows(engine):
    # Explicitly scoped to the reviewed 3c9 schema, not an incomplete current
    # backup. The current backup helper requires every PROTECTED_TABLE.
    tables = set(PROTECTED_TABLES) - {"chat_mensagens", "movimentos_quadro"}
    with engine.connect() as connection:
        return {table: tuple(connection.exec_driver_sql(
            f"SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'' ORDER BY row_to_json(t)::text),'')) FROM public.{table} t"
        ).one()) for table in sorted(tables)}


def rehearse(value, container, label):
    url = make_url(require_isolated_database(value))
    if url.host != "127.0.0.1" or set(url.query) & {"host", "hostaddr", "port"}:
        raise ValueError("Unambiguous IPv4 loopback required")
    if docker("inspect", "--format", '{{index .Config.Labels "automatize.audit"}}', container) != label:
        raise ValueError("Reviewed disposable container required")
    if docker("port", container, "5432/tcp") != f"127.0.0.1:{url.port}":
        raise ValueError("Container endpoint mismatch")
    legacy_name = f"legacy_{uuid4().hex}_test"
    target_name = f"upgraded_{uuid4().hex}_test"
    archive = f"/tmp/{legacy_name}.dump"
    docker("exec", container, "createdb", "-U", "postgres", legacy_name)
    legacy = create_engine(url.set(database=legacy_name), hide_parameters=True)
    target = create_engine(url.set(database=target_name), hide_parameters=True)
    try:
        migrate(legacy, "3c9e7a1b5d20")
        owner, technician, admin, pending, accepted, occurrence = [uuid4() for _ in range(6)]
        with legacy.begin() as connection:
            for user, profile in ((owner, "CLIENTE"), (technician, "TECNICO"), (admin, "ADMIN")):
                connection.execute(text("INSERT INTO public.users(id,nome,email,senha_hash,perfil) VALUES (:id,'Synthetic',:email,'unused',:profile)"),
                                   {"id": user, "email": f"{user}@test.invalid", "profile": profile})
            for pedido, estado in ((pending, "PLANEAMENTO"), (accepted, "HOMOLOGACAO")):
                connection.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id,responsavel_id,status) VALUES (:id,:code,'Synthetic legacy',:owner,:tech,:state)"),
                                   {"id": pedido, "code": str(pedido), "owner": owner, "tech": technician, "state": estado})
            connection.execute(text("INSERT INTO public.etapas_operacionais(pedido_id,descricao,concluida,concluida_em,concluida_por_id,criado_por_id) VALUES (:pedido,'Synthetic complete',true,now(),:tech,:admin)"),
                               {"pedido": accepted, "tech": technician, "admin": admin})
            connection.execute(text("INSERT INTO public.aceites_formais(pedido_id,cliente_id,versao_entregavel,declaracao_aceite,hash_validacao) VALUES (:pedido,:owner,'legacy-v1','Aceite sintético preservado','synthetic-digest')"),
                               {"pedido": accepted, "owner": owner})
            connection.execute(text("UPDATE public.pedidos SET status='CONCLUIDO',percentual_progresso=100 WHERE id=:id"), {"id": accepted})
            connection.execute(text("INSERT INTO public.auditoria_logs(usuario_id,pedido_id,acao) VALUES (:owner,:pedido,'SYNTHETIC_LEGACY_ACCEPTANCE')"), {"owner": owner, "pedido": accepted})
            connection.execute(text("INSERT INTO public.historico_status_pedidos(pedido_id,usuario_id,status_anterior,status_novo) VALUES (:pedido,:owner,'HOMOLOGACAO','CONCLUIDO')"), {"owner": owner, "pedido": accepted})
            connection.execute(text("INSERT INTO public.ocorrencias(id,pedido_id,autor_id,tipo,descricao) VALUES (:id,:pedido,:owner,'ERRO','Synthetic occurrence')"), {"id": occurrence, "pedido": pending, "owner": owner})
            connection.execute(text("INSERT INTO public.anexos(pedido_id,ocorrencia_id,enviado_por_id,nome_arquivo,caminho_storage,extensao,tamanho_bytes) VALUES (:pedido,:occurrence,:owner,'synthetic.png',:path,'png',1)"),
                               {"pedido": pending, "occurrence": occurrence, "owner": owner, "path": f"pedidos/{pending}/{uuid4()}.png"})
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role")
            connection.exec_driver_sql("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon,authenticated,service_role")
            connection.exec_driver_sql("GRANT SELECT(nome),UPDATE(nome) ON public.users TO PUBLIC")
            connection.exec_driver_sql("GRANT SELECT(descricao),UPDATE(descricao) ON public.etapas_operacionais TO anon,authenticated")
            for table in PROTECTED_TABLES:
                if table in {"chat_mensagens", "movimentos_quadro"}:
                    continue
                mode = "DISABLE" if table in {"etapas_operacionais", "historico_status_pedidos", "alembic_version"} else "ENABLE"
                connection.exec_driver_sql(f"ALTER TABLE public.{table} {mode} ROW LEVEL SECURITY")
        before = legacy_rows(legacy)
        security_before = security_fingerprint(legacy)
        docker("exec", container, "pg_dump", "-U", "postgres", "-d", legacy_name, "--format=custom", f"--file={archive}")
        docker("exec", container, "createdb", "-U", "postgres", target_name)
        docker("exec", container, "pg_restore", "-U", "postgres", "-d", target_name, "--exit-on-error", archive)
        if before != legacy_rows(target) or security_before != security_fingerprint(target):
            raise RuntimeError("Legacy rows/ACLs/schema not preserved by restore")
        migrate(target, "head")
        after = fingerprint(target)
        if any(after[t] != before[t] for t in before if t not in {"alembic_version", "pedidos", "etapas_operacionais", "ocorrencias"}):
            raise RuntimeError("Unexpected legacy evidence mutation")
        # Published migrations add columns/backfill ordem to these three tables.
        if any(after[t][0] != before[t][0] for t in before):
            raise RuntimeError("Legacy row counts changed")
        with target.connect() as connection:
            findings = assess_access(inspect_access(connection))
            role = dict(connection.exec_driver_sql("SELECT current_user AS runtime_test_role,session_user AS session_test_role").mappings().one())
            if findings:
                raise RuntimeError("Data API protection differs after legacy upgrade")
            version = connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one()
        with Session(target) as db:
            cliente = db.get(User, owner)
            tecnico = db.get(User, technician)
            administrador = db.get(User, admin)
            service = DemandService(db)
            pedido = service.criar(cliente, titulo="Release smoke", descricao="Synthetic restored SQL role smoke")
            pedido_id = pedido.id
            service.atribuir_responsavel(administrador, pedido_id, responsavel_id=technician)
            etapa = service.adicionar_etapa(tecnico, pedido_id, descricao="Validate restored release")
            etapa_id = etapa.id
            service.alterar_status(tecnico, pedido_id, StatusPedidoEnum.EXECUCAO)
            service.concluir_etapa(tecnico, pedido_id, etapa_id)
            if not service.listar_etapas(tecnico, pedido_id):
                raise RuntimeError("Stage read failed")
            service.alterar_status(tecnico, pedido_id, StatusPedidoEnum.HOMOLOGACAO)
            service.aprovar_homologacao(cliente, pedido_id, versao_entregavel="release-v1", declaracao_aceite="Aceito a entrega sintética restaurada.")
            db.add(ChatMensagem(id=uuid4(), pedido_id=pedido_id, autor_id=owner, canal="cliente", texto="Synthetic backup coverage"))
            db.add(MovimentoQuadro(id=uuid4(), conteudo_cifrado=b"synthetic opaque backup bytes"))
            db.commit()
        restored = validate(target.url.render_as_string(hide_password=False), container, label)
        return {"synthetic_legacy_revision": "3c9e7a1b5d20", "upgraded_revision": version,
                "legacy_snapshot_restore_equal": True, "legacy_row_counts_preserved": True,
                "old_acl_and_rls_reproduced": True, "backend_flow_validated": True,
                "current_backup_restore": restored, "tables_fingerprinted": sorted(PROTECTED_TABLES),
                "sql_test_identity": role, "production_role_equivalence_proven": False,
                "production_snapshot_used": False, "shared_supabase_accessed": False,
                "storage_bytes_restored": False}
    finally:
        legacy.dispose()
        target.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--audit-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = rehearse(os.environ.get("TEST_DATABASE_URL", ""), args.container, args.audit_label)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({"validated": False, "error": "Isolated release rehearsal failed; no shared environment used"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
