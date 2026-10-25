"""Rotas de escrita com JWT real e PostgreSQL real (Storage simulado)."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select # type: ignore

from app.api.v1.endpoints.demandas_acoes import get_demand_service
from app.core.config import Settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.domain.models import AceiteFormal, AuditoriaLog
from app.domain.models.enums import PerfilEnum
from app.main import create_app
from app.services.anexo_service import AnexoService
from app.services.demand_service import DemandService
from tests import amostras
from tests.integration.conftest import TEST_DATABASE_URL


SECRET = "integracao-demandas-" + "x" * 32


@pytest.fixture
def settings():
    return Settings(_env_file=None, DATABASE_URL=TEST_DATABASE_URL, JWT_SECRET_KEY=SECRET)


@pytest.fixture
def client(db, storage, settings):
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_demand_service] = lambda: DemandService(
        db, anexo_service=AnexoService(db, storage=storage)
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def atores(criar_usuario):
    return {
        "admin": criar_usuario(PerfilEnum.ADMIN),
        "cliente": criar_usuario(PerfilEnum.CLIENTE),
        "outro_cliente": criar_usuario(PerfilEnum.CLIENTE),
        "tecnico": criar_usuario(PerfilEnum.TECNICO),
    }


@pytest.fixture
def auth(atores, settings):
    return {
        nome: {"Authorization": f"Bearer {create_access_token(str(usuario.id), settings)}"}
        for nome, usuario in atores.items()
    }


@pytest.fixture
def demanda_id(client, auth, atores):
    resposta = client.post("/demandas", headers=auth["cliente"],
                           json={"titulo": "Manutencao notebook", "descricao": "Troca de pasta termica"})
    assert resposta.status_code == 201, resposta.text
    demanda_id = resposta.json()["id"]
    resposta = client.put(f"/demandas/{demanda_id}/responsavel", headers=auth["admin"],
                          json={"responsavel_id": str(atores["tecnico"].id)})
    assert resposta.status_code == 200, resposta.text
    return demanda_id


def _homologar(client, auth, demanda_id):
    for status in ("EXECUCAO", "HOMOLOGACAO"):
        resposta = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"], json={"status": status})
        assert resposta.status_code == 200, resposta.text


ACEITE = {"versao_entregavel": "v1.0", "declaracao_aceite": "Aprovo a entrega conforme combinado."}


def test_rotas_de_escrita_exigem_token(client, demanda_id):
    assert client.post("/demandas", json={"titulo": "Ajuste", "descricao": "Ajuste na base"}).status_code == 401
    assert client.post(f"/demandas/{demanda_id}/aceite", json=ACEITE).status_code == 401
    assert client.post(f"/demandas/{demanda_id}/status", json={"status": "EXECUCAO"}).status_code == 401


def test_cliente_da_demanda_vem_do_token(client, auth, atores):
    resposta = client.post("/demandas", headers=auth["cliente"],
                           json={"titulo": "Ajuste", "descricao": "Ajuste na base"})
    assert resposta.json()["cliente_id"] == str(atores["cliente"].id)

    resposta = client.post("/demandas", headers=auth["cliente"], json={
        "titulo": "Ajuste", "descricao": "Ajuste na base", "cliente_id": str(atores["outro_cliente"].id),
    })
    assert resposta.status_code == 403


def test_aceite_usa_cliente_autenticado_e_ignora_corpo(client, db, auth, atores, demanda_id):
    _homologar(client, auth, demanda_id)

    forjado = client.post(f"/demandas/{demanda_id}/aceite", headers=auth["outro_cliente"],
                          json=ACEITE | {"cliente_id": str(atores["cliente"].id)})
    assert forjado.status_code == 422  # campo desconhecido no corpo e recusado

    assert client.post(f"/demandas/{demanda_id}/aceite", headers=auth["outro_cliente"],
                       json=ACEITE).status_code == 404
    assert client.post(f"/demandas/{demanda_id}/aceite", headers=auth["admin"], json=ACEITE).status_code == 403
    assert client.post(f"/demandas/{demanda_id}/aceite", headers=auth["tecnico"], json=ACEITE).status_code == 403

    resposta = client.post(f"/demandas/{demanda_id}/aceite", headers=auth["cliente"], json=ACEITE)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["cliente_id"] == str(atores["cliente"].id)
    assert len(resposta.json()["hash_validacao"]) == 64

    assert client.get(f"/demandas/{demanda_id}", headers=auth["cliente"]).json()["status"] == "CONCLUIDO"
    assert client.post(f"/demandas/{demanda_id}/aceite", headers=auth["cliente"], json=ACEITE).status_code == 409
    assert client.patch(f"/demandas/{demanda_id}", headers=auth["cliente"],
                        json={"titulo": "Novo", "descricao": "Nova descricao"}).status_code == 409
    assert client.delete(f"/demandas/{demanda_id}", headers=auth["admin"]).status_code == 409
    assert db.scalar(select(AceiteFormal).where(AceiteFormal.cliente_id == atores["cliente"].id)) is not None


def test_status_concluido_nao_e_atalho_para_o_aceite(client, auth, demanda_id):
    _homologar(client, auth, demanda_id)
    resposta = client.post(f"/demandas/{demanda_id}/status", headers=auth["admin"], json={"status": "CONCLUIDO"})
    assert resposta.status_code == 403
    assert "aceite formal" in resposta.json()["detail"]


def test_etapas_pendentes_bloqueiam_homologacao(client, auth, demanda_id):
    client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"], json={"status": "EXECUCAO"})
    etapa = client.post(f"/demandas/{demanda_id}/etapas", headers=auth["tecnico"],
                        json={"descricao": "Testar temperatura"}).json()

    bloqueada = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"], json={"status": "HOMOLOGACAO"})
    assert bloqueada.status_code == 409
    assert "Testar temperatura" in bloqueada.json()["detail"]

    concluida = client.post(f"/demandas/{demanda_id}/etapas/{etapa['id']}/conclusao", headers=auth["tecnico"])
    assert concluida.json()["concluida"] is True
    liberada = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"], json={"status": "HOMOLOGACAO"})
    assert liberada.status_code == 200
    assert liberada.json()["percentual_progresso"] == "85.00"


def test_rejeicao_pela_api(client, auth, demanda_id):
    _homologar(client, auth, demanda_id)
    assert client.post(f"/demandas/{demanda_id}/rejeicao", headers=auth["cliente"],
                       json={"motivo": "Curto"}).status_code == 409
    resposta = client.post(f"/demandas/{demanda_id}/rejeicao", headers=auth["cliente"],
                           json={"motivo": "Layout divergente do aprovado"})
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "EXECUCAO"


def test_upload_de_evidencia_valida_conteudo(client, auth, storage, demanda_id):
    valido = client.post(f"/demandas/{demanda_id}/evidencias", headers=auth["cliente"],
                         files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/octet-stream")})
    assert valido.status_code == 201, valido.text
    assert valido.json()["extensao"] == "pdf"
    assert [tipo for _, tipo in storage.arquivos.values()] == ["application/pdf"]

    disfarcado = client.post(f"/demandas/{demanda_id}/evidencias", headers=auth["cliente"],
                             files={"arquivo": ("foto.png", b"MZ\x90\x00 executavel", "image/png")})
    assert disfarcado.status_code == 422
    assert len(storage.arquivos) == 1


def test_historico_somente_leitura_com_autores(client, auth, atores, demanda_id):
    resposta = client.get(f"/demandas/{demanda_id}/historico", headers=auth["cliente"])
    assert resposta.status_code == 200
    registros = resposta.json()
    assert [r["acao"] for r in registros] == ["CRIACAO_DEMANDA", "ATRIBUICAO_RESPONSAVEL"]
    assert [r["usuario_id"] for r in registros] == [str(atores["cliente"].id), str(atores["admin"].id)]

    assert client.get(f"/demandas/{demanda_id}/historico", headers=auth["outro_cliente"]).status_code == 404
    assert client.get(f"/demandas/{uuid4()}/historico", headers=auth["admin"]).status_code == 404
