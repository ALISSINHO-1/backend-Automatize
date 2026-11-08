from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_migration_upgrade import fresh_database, upgrade


@pytest.mark.parametrize("consistent", [True, False], ids=["preserve-valid-rows", "abort-on-invalid-legacy"])
def test_attachment_migration_preserves_data_or_aborts_without_repair(engine, monkeypatch, consistent):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch, "b6e1c8a4d230")
        user, first, second, occurrence = uuid4(), uuid4(), uuid4(), uuid4()
        with scratch.begin() as c:
            c.execute(text("INSERT INTO public.users(id,nome,email,senha_hash) VALUES (:id,'Synthetic',:email,'unused')"),
                      {"id": user, "email": f"{user}@test.invalid"})
            for order in (first, second):
                c.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,:code,'Synthetic',:user)"),
                          {"id": order, "code": str(order), "user": user})
            c.execute(text("INSERT INTO public.ocorrencias(id,pedido_id,autor_id,tipo,descricao) VALUES (:id,:order,:user,'ERRO','Synthetic')"),
                      {"id": occurrence, "order": first, "user": user})
            c.execute(text("INSERT INTO public.anexos(pedido_id,ocorrencia_id,enviado_por_id,nome_arquivo,caminho_storage,extensao,tamanho_bytes) "
                           "VALUES (:order,:occurrence,:user,'synthetic.pdf','synthetic','pdf',1)"),
                      {"order": first if consistent else second, "occurrence": occurrence, "user": user})
        if consistent:
            config = upgrade(scratch, monkeypatch)
            command.check(config)
        else:
            with pytest.raises(DBAPIError) as error:
                upgrade(scratch, monkeypatch)
            assert error.value.orig.pgcode == "23514"
        with scratch.connect() as c:
            assert c.exec_driver_sql("SELECT count(*) FROM public.anexos").scalar_one() == 1
            expected = "84db17ce9f26" if consistent else "b6e1c8a4d230"
            assert c.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one() == expected
    finally:
        scratch.dispose()
