from uuid import UUID

from app.core.security import create_access_token
from app.domain.models.enums import PerfilEnum
from app.domain.models.pedido import Pedido
from tests.integration.test_demandas_acoes_api import atores, auth, client, demanda_id, settings  # noqa: F401


def test_chat_separa_canais_e_valida_vinculo(
    client, db, auth, atores, demanda_id, criar_usuario, settings
):
    externo = f"/demandas/{demanda_id}/chat/cliente"
    interno = f"/demandas/{demanda_id}/chat/interno"
    assert client.get(externo).status_code == 401

    for canal, perfil, texto in (
        (externo, "cliente", "  Mensagem do cliente  "),
        (interno, "admin", "Mensagem interna"),
    ):
        resposta = client.post(canal, headers=auth[perfil], json={"texto": texto})
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["autor_id"] == str(atores[perfil].id)
        assert resposta.json()["texto"] == texto.strip()
        historico = client.get(canal, headers=auth["tecnico"]).json()
        assert historico == {"mensagens": [resposta.json()], "antes_de": None}

    for canal, perfil in ((externo, "admin"), (externo, "outro_cliente"), (interno, "cliente")):
        assert client.get(canal, headers=auth[perfil]).status_code == 404
        assert client.post(canal, headers=auth[perfil], json={"texto": "Bloqueada"}).status_code == 404

    outro = criar_usuario(PerfilEnum.TECNICO)
    token_outro = {"Authorization": f"Bearer {create_access_token(str(outro.id), settings)}"}
    assert client.get(interno, headers=token_outro).status_code == 404
    pedido = db.get(Pedido, UUID(demanda_id))
    pedido.responsavel_id = outro.id
    db.commit()
    assert client.get(interno, headers=auth["tecnico"]).status_code == 404
    assert client.get(interno, headers=token_outro).status_code == 200


def test_chat_pagina_historico_e_rejeita_mensagem_vazia(client, auth, demanda_id):
    externo = f"/demandas/{demanda_id}/chat/cliente"
    cliente = auth["cliente"]
    assert client.post(externo, headers=cliente, json={"texto": " "}).status_code == 422
    for texto in ("Primeira", "Segunda"):
        assert client.post(externo, headers=cliente, json={"texto": texto}).status_code == 201
    primeira_pagina = client.get(externo, headers=cliente, params={"limite": 1}).json()
    anterior = client.get(
        externo, headers=cliente, params={"limite": 1, "antes_de": primeira_pagina["antes_de"]}
    ).json()
    assert {primeira_pagina["mensagens"][0]["texto"], anterior["mensagens"][0]["texto"]} == {
        "Primeira", "Segunda",
    }
    assert anterior["antes_de"] is None


def test_fila_tecnica_libera_chat_depois_de_assumir(client, db, auth, criar_usuario, settings):
    fila = "/demandas/chat/fila"
    assert client.get(fila).status_code == 401
    for papel in ("cliente", "admin"):
        assert client.get(fila, headers=auth[papel]).status_code == 403

    criado = client.post(
        "/demandas", headers=auth["cliente"],
        json={"titulo": "Demanda na fila", "descricao": "Descrição reservada"},
    )
    assert criado.status_code == 201
    dados = criado.json()
    demanda = f"/demandas/{dados['id']}"
    canal = f"{demanda}/chat/cliente"
    assert client.get(canal, headers=auth["tecnico"]).status_code == 404
    assert client.get(canal, headers=auth["cliente"]).status_code == 409
    assert client.post(f"{demanda}/assumir", headers=auth["cliente"]).status_code == 403
    fila_tecnica = client.get(fila, headers=auth["tecnico"]).json()
    assert [item for item in fila_tecnica if item["id"] == dados["id"]] == [{
        "id": dados["id"], "codigo_identificador": dados["codigo_identificador"],
        "titulo": dados["titulo"],
    }]

    assert client.post(f"{demanda}/assumir", headers=auth["tecnico"]).status_code == 204
    assert client.post(f"{demanda}/assumir", headers=auth["tecnico"]).status_code == 204
    assert all(item["id"] != dados["id"] for item in client.get(fila, headers=auth["tecnico"]).json())
    outro = criar_usuario(PerfilEnum.TECNICO)
    token = {"Authorization": f"Bearer {create_access_token(str(outro.id), settings)}"}
    db.commit()
    assert client.post(f"{demanda}/assumir", headers=token).status_code == 409
    assert client.get(canal, headers=token).status_code == 404
    assert client.get(canal, headers=auth["cliente"]).status_code == 200
    assert client.get(canal, headers=auth["tecnico"]).status_code == 200
    assert client.get(f"{demanda}/chat/interno", headers=auth["admin"]).status_code == 200
