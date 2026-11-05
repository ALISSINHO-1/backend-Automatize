from uuid import uuid4

from sqlalchemy import text

from tests.integration.test_migration_upgrade import fresh_database, upgrade


def test_backfill_preserva_ordem_e_dados(engine, monkeypatch):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch, "e3b7c1d9f402")
        usuario, pedido = uuid4(), uuid4()
        primeira, segunda = uuid4(), uuid4()
        with scratch.begin() as db:
            db.execute(text("INSERT INTO users(id,nome,email,senha_hash) VALUES (:id,'Teste',:email,'unused')"),
                       {"id": usuario, "email": f"{usuario}@test.invalid"})
            db.execute(text("INSERT INTO pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,'MIG-1','Teste',:cliente)"),
                       {"id": pedido, "cliente": usuario})
            for identificador, data in ((segunda, "2026-01-02"), (primeira, "2026-01-01")):
                db.execute(text("""INSERT INTO etapas_operacionais(id,pedido_id,descricao,criado_por_id,created_at)
                                   VALUES (:id,:pedido,'Etapa preservada',:usuario,:data)"""),
                           {"id": identificador, "pedido": pedido, "usuario": usuario, "data": data})
        upgrade(scratch, monkeypatch)
        with scratch.connect() as db:
            etapas = db.execute(text("SELECT id,ordem FROM etapas_operacionais ORDER BY ordem")).all()
            assert etapas == [(primeira, 1), (segunda, 2)]
    finally:
        scratch.dispose()
