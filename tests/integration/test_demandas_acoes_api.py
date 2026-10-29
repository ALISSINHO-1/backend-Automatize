"""Rotas de escrita com JWT real e PostgreSQL real (Storage simulado)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select  # type: ignore

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
    return Settings(
        _env_file=None, DATABASE_URL=TEST_DATABASE_URL, JWT_SECRET_KEY=SECRET
    )


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
        nome: {
            "Authorization": f"Bearer {create_access_token(str(usuario.id), settings)}"
        }
        for nome, usuario in atores.items()
    }


@pytest.fixture
def demanda_id(client, auth, atores):
    resposta = client.post(
        "/demandas",
        headers=auth["cliente"],
        json={"titulo": "Manutencao notebook", "descricao": "Troca de pasta termica"},
    )
    assert resposta.status_code == 201, resposta.text
    demanda_id = resposta.json()["id"]
    resposta = client.put(
        f"/demandas/{demanda_id}/responsavel",
        headers=auth["admin"],
        json={"responsavel_id": str(atores["tecnico"].id)},
    )
    assert resposta.status_code == 200, resposta.text
    return demanda_id


def _homologar(client, auth, demanda_id):
    resposta = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "EXECUCAO"},
    )
    assert resposta.status_code == 200, resposta.text
    etapa = client.post(
        f"/demandas/{demanda_id}/etapas",
        headers=auth["tecnico"],
        json={"descricao": "Executar servico"},
    ).json()
    client.post(
        f"/demandas/{demanda_id}/etapas/{etapa['id']}/conclusao",
        headers=auth["tecnico"],
    )
    resposta = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "HOMOLOGACAO"},
    )
    assert resposta.status_code == 200, resposta.text


ACEITE = {
    "versao_entregavel": "v1.0",
    "declaracao_aceite": "Aprovo a entrega conforme combinado.",
}


def test_rotas_de_escrita_exigem_token(client, demanda_id):
    assert (
        client.post(
            "/demandas", json={"titulo": "Ajuste", "descricao": "Ajuste na base"}
        ).status_code
        == 401
    )
    assert client.post(f"/demandas/{demanda_id}/aceite", json=ACEITE).status_code == 401
    assert (
        client.post(
            f"/demandas/{demanda_id}/status", json={"status": "EXECUCAO"}
        ).status_code
        == 401
    )


def test_cliente_da_demanda_vem_do_token(client, auth, atores):
    resposta = client.post(
        "/demandas",
        headers=auth["cliente"],
        json={"titulo": "Ajuste", "descricao": "Ajuste na base"},
    )
    assert resposta.json()["cliente_id"] == str(atores["cliente"].id)

    resposta = client.post(
        "/demandas",
        headers=auth["cliente"],
        json={
            "titulo": "Ajuste",
            "descricao": "Ajuste na base",
            "cliente_id": str(atores["outro_cliente"].id),
        },
    )
    assert resposta.status_code == 403


def test_aceite_usa_cliente_autenticado_e_ignora_corpo(
    client, db, auth, atores, demanda_id
):
    _homologar(client, auth, demanda_id)

    forjado = client.post(
        f"/demandas/{demanda_id}/aceite",
        headers=auth["outro_cliente"],
        json=ACEITE | {"cliente_id": str(atores["cliente"].id)},
    )
    assert forjado.status_code == 422  # campo desconhecido no corpo e recusado

    assert (
        client.post(
            f"/demandas/{demanda_id}/aceite", headers=auth["outro_cliente"], json=ACEITE
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/demandas/{demanda_id}/aceite", headers=auth["admin"], json=ACEITE
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/demandas/{demanda_id}/aceite", headers=auth["tecnico"], json=ACEITE
        ).status_code
        == 403
    )

    resposta = client.post(
        f"/demandas/{demanda_id}/aceite", headers=auth["cliente"], json=ACEITE
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["cliente_id"] == str(atores["cliente"].id)
    assert len(resposta.json()["hash_validacao"]) == 64

    assert (
        client.get(f"/demandas/{demanda_id}", headers=auth["cliente"]).json()["status"]
        == "CONCLUIDO"
    )
    assert (
        client.post(
            f"/demandas/{demanda_id}/aceite", headers=auth["cliente"], json=ACEITE
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/demandas/{demanda_id}",
            headers=auth["cliente"],
            json={"titulo": "Novo", "descricao": "Nova descricao"},
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/demandas/{demanda_id}", headers=auth["admin"]).status_code
        == 409
    )
    assert (
        db.scalar(
            select(AceiteFormal).where(AceiteFormal.cliente_id == atores["cliente"].id)
        )
        is not None
    )


def test_status_concluido_nao_e_atalho_para_o_aceite(client, auth, demanda_id):
    _homologar(client, auth, demanda_id)
    resposta = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["admin"],
        json={"status": "CONCLUIDO"},
    )
    assert resposta.status_code == 403
    assert "aceite formal" in resposta.json()["detail"]


def test_etapas_pendentes_bloqueiam_homologacao(client, auth, demanda_id):
    client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "EXECUCAO"},
    )
    etapa = client.post(
        f"/demandas/{demanda_id}/etapas",
        headers=auth["tecnico"],
        json={"descricao": "Testar temperatura"},
    ).json()

    bloqueada = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "HOMOLOGACAO"},
    )
    assert bloqueada.status_code == 409
    assert "Testar temperatura" in bloqueada.json()["detail"]

    concluida = client.post(
        f"/demandas/{demanda_id}/etapas/{etapa['id']}/conclusao",
        headers=auth["tecnico"],
    )
    assert concluida.json()["concluida"] is True
    liberada = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "HOMOLOGACAO"},
    )
    assert liberada.status_code == 200
    assert liberada.json()["percentual_progresso"] == "85.00"


def test_homologacao_sem_etapas_e_recusada_pela_api(client, auth, demanda_id):
    client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "EXECUCAO"},
    )
    resposta = client.post(
        f"/demandas/{demanda_id}/status",
        headers=auth["tecnico"],
        json={"status": "HOMOLOGACAO"},
    )
    assert resposta.status_code == 409
    assert "sem etapas operacionais" in resposta.json()["detail"]
    assert (
        client.get(f"/demandas/{demanda_id}", headers=auth["cliente"]).json()["status"]
        == "EXECUCAO"
    )


def test_rejeicao_pela_api(client, auth, demanda_id):
    _homologar(client, auth, demanda_id)
    assert (
        client.post(
            f"/demandas/{demanda_id}/rejeicao",
            headers=auth["cliente"],
            json={"motivo": "Curto"},
        ).status_code
        == 409
    )
    resposta = client.post(
        f"/demandas/{demanda_id}/rejeicao",
        headers=auth["cliente"],
        json={"motivo": "Layout divergente do aprovado"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "EXECUCAO"


def test_upload_de_evidencia_valida_conteudo(client, auth, storage, demanda_id):
    valido = client.post(
        f"/demandas/{demanda_id}/evidencias",
        headers=auth["cliente"],
        files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/octet-stream")},
    )
    assert valido.status_code == 201, valido.text
    assert valido.json()["extensao"] == "pdf"
    assert [tipo for _, tipo in storage.arquivos.values()] == ["application/pdf"]

    disfarcado = client.post(
        f"/demandas/{demanda_id}/evidencias",
        headers=auth["cliente"],
        files={"arquivo": ("foto.png", b"MZ\x90\x00 executavel", "image/png")},
    )
    assert disfarcado.status_code == 422
    assert len(storage.arquivos) == 1


def test_historico_somente_leitura_com_autores(client, auth, atores, demanda_id):
    resposta = client.get(f"/demandas/{demanda_id}/historico", headers=auth["cliente"])
    assert resposta.status_code == 200
    registros = resposta.json()
    assert [r["acao"] for r in registros] == [
        "CRIACAO_DEMANDA",
        "ATRIBUICAO_RESPONSAVEL",
    ]
    assert [r["usuario_id"] for r in registros] == [
        str(atores["cliente"].id),
        str(atores["admin"].id),
    ]

    assert (
        client.get(
            f"/demandas/{demanda_id}/historico", headers=auth["outro_cliente"]
        ).status_code
        == 404
    )
    assert (
        client.get(f"/demandas/{uuid4()}/historico", headers=auth["admin"]).status_code
        == 404
    )


def test_put_preserva_campos_protegidos_e_isolamento(client, auth, demanda_id):
    url = f"/demandas/{demanda_id}"
    payload = {"titulo": "Título revisado", "descricao": "Descrição revisada do pedido"}
    assert (
        client.put(url, headers=auth["outro_cliente"], json=payload).status_code == 404
    )
    assert client.put(url, headers=auth["tecnico"], json=payload).status_code == 403
    assert (
        client.put(
            url, headers=auth["cliente"], json=payload | {"status": "CONCLUIDO"}
        ).status_code
        == 422
    )
    assert client.put(url, headers=auth["cliente"], json=payload).status_code == 200
    assert (
        client.get(url, headers=auth["cliente"]).json()["titulo"] == payload["titulo"]
    )


def test_ocorrencias_vinculo_autoria_auditoria_e_rollback(
    client, db, auth, atores, demanda_id
):
    url = f"/demandas/{demanda_id}/ocorrencias"
    payload = {"tipo": "ERRO", "descricao": "Falha ao calcular os totais"}
    assert client.post(url, json=payload).status_code == 401
    assert (
        client.post(url, headers=auth["outro_cliente"], json=payload).status_code == 404
    )
    assert (
        client.post(
            url,
            headers=auth["cliente"],
            json=payload | {"autor_id": str(atores["admin"].id)},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, headers=auth["cliente"], json=payload | {"tipo": "REGRESSO_ESTADO"}
        ).status_code
        == 422
    )
    criada = client.post(url, headers=auth["cliente"], json=payload)
    assert criada.status_code == 201, criada.text
    assert criada.json()["autor_id"] == str(atores["cliente"].id)
    oid = criada.json()["id"]
    assert client.get(url, headers=auth["cliente"]).json()[0]["id"] == oid
    assert client.get(f"{url}/{oid}", headers=auth["outro_cliente"]).status_code == 404
    assert (
        client.get(
            f"/demandas/{uuid4()}/ocorrencias/{oid}", headers=auth["admin"]
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"{url}/{oid}",
            headers=auth["tecnico"],
            json={"descricao": "Tentativa não autorizada"},
        ).status_code
        == 403
    )
    assert (
        client.get(f"{url}/{oid}", headers=auth["cliente"]).json()["descricao"]
        == payload["descricao"]
    )
    assert (
        client.put(
            f"{url}/{oid}",
            headers=auth["cliente"],
            json={"descricao": "Descrição corrigida pelo autor"},
        ).status_code
        == 200
    )
    acoes = [
        r["acao"]
        for r in client.get(
            f"/demandas/{demanda_id}/historico", headers=auth["cliente"]
        ).json()
    ]
    assert acoes.count("CRIACAO_OCORRENCIA") == 1
    assert acoes.count("EDICAO_OCORRENCIA") == 1
    _homologar(client, auth, demanda_id)
    assert (
        client.post(
            f"/demandas/{demanda_id}/aceite", headers=auth["cliente"], json=ACEITE
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"{url}/{oid}",
            headers=auth["cliente"],
            json={"descricao": "Editar após concluir"},
        ).status_code
        == 409
    )
    assert client.post(url, headers=auth["cliente"], json=payload).status_code == 409


def test_anexos_listagem_sem_chaves_e_acesso_autorizado(
    client, auth, storage, demanda_id
):
    url = f"/demandas/{demanda_id}/anexos"
    assert client.get(url, headers=auth["cliente"]).json() == []
    assert client.get(url, headers=auth["outro_cliente"]).status_code == 404
    criado = client.post(
        f"/demandas/{demanda_id}/evidencias",
        headers=auth["cliente"],
        files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/pdf")},
    )
    assert criado.status_code == 201, criado.text
    anexos = client.get(url, headers=auth["cliente"]).json()
    assert len(anexos) == 1 and "caminho_storage" not in anexos[0]
    aid = anexos[0]["id"]
    chamadas = []

    def assinar(caminho, *, expires_in):
        chamadas.append((caminho, expires_in))
        return "https://storage.example/signed?token=temporario"

    storage.signed_url = assinar
    assert (
        client.get(
            f"{url}/{aid}/acesso", headers=auth["outro_cliente"], follow_redirects=False
        ).status_code
        == 404
    )
    assert chamadas == []
    resposta = client.get(
        f"{url}/{aid}/acesso", headers=auth["cliente"], follow_redirects=False
    )
    assert (
        resposta.status_code == 307 and resposta.headers["cache-control"] == "no-store"
    )
    assert chamadas[0][1] == 60
    assert (
        client.get(
            f"{url}/{uuid4()}/acesso", headers=auth["cliente"], follow_redirects=False
        ).status_code
        == 404
    )


def test_filtros_totais_nao_paginados_e_sem_vazamento(client, auth, atores, demanda_id):
    for i in range(3):
        assert (
            client.post(
                "/demandas",
                headers=auth["cliente"],
                json={
                    "titulo": f"Relatório {i}",
                    "descricao": "Relatório de vendas mensal",
                },
            ).status_code
            == 201
        )
    client.post(
        "/demandas",
        headers=auth["outro_cliente"],
        json={
            "titulo": "Relatório alheio",
            "descricao": "Não deve aparecer na contagem",
        },
    )
    response = client.get(
        "/demandas",
        headers=auth["cliente"],
        params={"busca": "Relatório", "incluir_totais": True, "limit": 1},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1 and response.headers["X-Total-Count"] == "3"
    assert all(r["cliente_id"] == str(atores["cliente"].id) for r in response.json())
    response = client.get(
        "/demandas",
        headers=auth["cliente"],
        params={"cliente_id": str(atores["outro_cliente"].id), "incluir_totais": True},
    )
    assert response.json() == [] and response.headers["X-Total-Count"] == "0"
    assert (
        client.get(
            "/demandas",
            headers=auth["cliente"],
            params={"inicio": "2026-10-30T00:00:00Z", "fim": "2026-10-29T00:00:00Z"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/demandas",
            headers=auth["cliente"],
            params={"inicio": "2026-10-29T00:00:00"},
        ).status_code
        == 422
    )
    response = client.get(
        "/demandas",
        headers=auth["cliente"],
        params={"busca": "%", "incluir_totais": True},
    )
    assert response.json() == []
