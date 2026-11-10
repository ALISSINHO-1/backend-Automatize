"""Hardening from the local chat, preserving HML routes and participant policy."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.chat import _validar_conversa
from app.domain.models import ChatMensagem, Pedido, User
from app.domain.models.enums import PerfilEnum
from fastapi import HTTPException
from tests.integration.test_demandas_acoes_api import settings, client, atores, auth, demanda_id  # noqa: F401
from tests.integration.test_concurrency_postgres import committed_order  # noqa: F401


@pytest.mark.parametrize("payload", [
    {"texto": "ok", "autor_id": str(uuid4())},
    {"texto": "ok", "pedido_id": str(uuid4())},
    {"texto": "nulo\x00"}, {"texto": "x" * 2001}, {"texto": " \t\n"},
], ids=["forged-author", "forged-demand", "null-byte", "above-limit", "blank"])
def test_chat_recusa_campos_forjados_e_conteudo_invalido(client, auth, demanda_id, payload):
    assert client.post(f"/demandas/{demanda_id}/chat/cliente", headers=auth["cliente"], json=payload).status_code == 422


@pytest.mark.parametrize("perfil,canal", [("cliente", "cliente"), ("tecnico", "cliente"), ("tecnico", "interno"), ("admin", "interno")])
def test_chat_autor_e_campos_seguros(client, db, auth, atores, demanda_id, perfil, canal):
    response = client.post(f"/demandas/{demanda_id}/chat/{canal}", headers=auth[perfil], json={"texto": "Mensagem integrada"})
    assert response.status_code == 201
    assert set(response.json()) == {"id", "autor_id", "autor_nome", "texto", "criado_em"}
    assert response.json()["autor_id"] == str(atores[perfil].id)
    saved = db.scalar(select(ChatMensagem).where(ChatMensagem.pedido_id == demanda_id))
    assert str(saved.autor_id) == str(atores[perfil].id) and saved.canal == canal


@pytest.mark.parametrize("invalid", [False, True], ids=["expired", "invalid-signature"])
def test_chat_rejeita_jwt_expirado_ou_invalido(client, settings, atores, demanda_id, invalid):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(atores["cliente"].id), "iat": now-timedelta(hours=2), "exp": now-timedelta(hours=1)}
    token = jwt.encode(claims, "wrong-key-" * 8 if invalid else settings.JWT_SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": "Bearer " + token}
    path = f"/demandas/{demanda_id}/chat/cliente"
    assert client.get(path, headers=headers).status_code == 401
    assert client.post(path, headers=headers, json={"texto": "Bloqueada"}).status_code == 401


def test_cursor_de_outro_canal_nao_revela_historico(client, auth, demanda_id):
    base = f"/demandas/{demanda_id}/chat"
    internal = client.post(base+"/interno", headers=auth["admin"], json={"texto": "Reservada"}).json()["id"]
    assert client.get(base+"/cliente", headers=auth["cliente"], params={"antes_de": internal}).status_code == 404
    assert client.get(base+"/interno", headers=auth["cliente"]).status_code == 404
    assert client.get(base+"/cliente", headers=auth["tecnico"], params={"limite": 101}).status_code == 422


def test_chat_revalida_demanda_ja_carregada_apos_reatribuicao(engine, committed_order):
    _, _, pedido_id = committed_order
    old_id, new_id = uuid4(), uuid4()
    with Session(engine) as writer:
        writer.add_all([User(id=id, nome="Synthetic technician", email=f"{id}@test.invalid",
                             senha_hash="unused", perfil=PerfilEnum.TECNICO, ativo=True) for id in (old_id,new_id)])
        writer.commit()
        pedido = writer.get(Pedido, pedido_id)
        pedido.responsavel_id = old_id
        writer.commit()
    with Session(engine, expire_on_commit=False) as reader, Session(engine) as writer:
        cached = reader.get(Pedido, pedido_id)
        old = reader.get(User, old_id)
        reader.commit()
        changed = writer.get(Pedido, pedido_id)
        changed.responsavel_id = new_id
        writer.commit()
        assert cached.responsavel_id == old_id
        with pytest.raises(HTTPException) as denied:
            _validar_conversa(reader, pedido_id, "interno", old)
        assert denied.value.status_code == 404
