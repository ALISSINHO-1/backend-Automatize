"""Mesmos contratos exercitados em SQLite local e PostgreSQL no CI.

SQLite nao valida triggers, RLS ou concorrencia PostgreSQL; a suite integration
reexecuta estes cenarios no banco real junto dos testes existentes dessas regras.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.domain.models import AuditoriaLog, Pedido
from app.domain.models.enums import PerfilEnum
from app.services.demand_service import DemandService
from tests import amostras


def criar(client, auth, titulo="Demanda de teste", perfil="cliente"):
    resposta = client.post("/demandas", headers=auth[perfil],
                           json={"titulo": titulo, "descricao": "Descricao completa da demanda"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_filtros_e_totais_respeitam_escopo_antes_da_paginacao(client, auth, atores, demanda_id):
    criar(client, auth, "Demanda privada", "outro_cliente")
    for i in range(3):
        criar(client, auth, f"Fila especial {i}")
    parametros = {"cliente_id": str(atores["cliente"].id), "busca": "Fila especial", "status": "PLANEAMENTO"}
    pagina = client.get("/demandas", headers=auth["admin"], params=parametros | {"limit": 1, "offset": 1})
    assert pagina.status_code == 200, pagina.text
    assert len(pagina.json()) == 1
    indicadores = client.get("/demandas/indicadores", headers=auth["admin"], params=parametros).json()
    assert indicadores["total"] == 3
    assert indicadores["por_status"]["PLANEAMENTO"] == 3
    # Um filtro nunca substitui o UUID vindo do JWT.
    for perfil in ("cliente", "tecnico"):
        alheio = {"cliente_id": str(atores["outro_cliente"].id)}
        assert client.get("/demandas", headers=auth[perfil], params=alheio).json() == []
        assert client.get("/demandas/indicadores", headers=auth[perfil], params=alheio).json()["total"] == 0
    tecnico = {"responsavel_id": str(atores["tecnico"].id)}
    assert client.get("/demandas/indicadores", headers=auth["admin"], params=tecnico).json()["total"] == 1


def test_datas_e_busca_literal(client, auth, demanda_id, db):
    id_literal = criar(client, auth, "Teste 100%_literal")
    criar(client, auth, "Teste 100 qualquer literal")
    resposta = client.get("/demandas", headers=auth["cliente"], params={"busca": "%_"})
    assert [p["id"] for p in resposta.json()] == [id_literal]
    pedido = db.get(Pedido, UUID(demanda_id))
    pedido.created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    db.commit()
    intervalo = {"criado_de": "2026-01-01T12:00:00Z", "criado_ate": "2026-01-01T12:00:00Z"}
    resposta = client.get("/demandas", headers=auth["cliente"], params=intervalo)
    assert [p["id"] for p in resposta.json()] == [demanda_id]
    assert client.get("/demandas/indicadores", headers=auth["cliente"], params=intervalo).json()["total"] == 1


@pytest.mark.parametrize("params", [
    {"criado_de": "2026-02-01T00:00:00Z", "criado_ate": "2026-01-01T00:00:00Z"},
    {"criado_de": "2026-01-01"}, {"status": "INVALIDO"}, {"busca": "   "}, {"cliente_id": "xxx"},
])
def test_filtros_invalidos_retornam_422(client, auth, params):
    for rota in ("/demandas", "/demandas/indicadores"):
        resposta = client.get(rota, headers=auth["cliente"], params=params)
        assert resposta.status_code == 422, resposta.text


def test_etapas_ordem_edicao_remocao_e_auditoria(client, auth, demanda_id, db):
    url = f"/demandas/{demanda_id}/etapas"
    a = client.post(url, headers=auth["tecnico"], json={"descricao": "Primeira etapa"}).json()
    b = client.post(url, headers=auth["tecnico"], json={"descricao": "Segunda etapa", "ordem": 1}).json()
    assert a["ordem"] == 1
    assert b["ordem"] == 1
    assert [e["id"] for e in client.get(url, headers=auth["cliente"]).json()] == [b["id"], a["id"]]
    resposta = client.patch(f"{url}/{a['id']}", headers=auth["tecnico"],
                            json={"descricao": "Primeira revisada", "ordem": 1})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["descricao"] == "Primeira revisada"
    assert client.patch(f"{url}/{a['id']}", headers=auth["cliente"], json={"ordem": 1}).status_code == 403
    assert client.patch(f"{url}/{uuid4()}", headers=auth["tecnico"], json={"ordem": 1}).status_code == 404
    assert client.patch(f"{url}/{a['id']}", headers=auth["tecnico"], json={"ordem": 9}).status_code == 409
    assert client.patch(f"{url}/{a['id']}", headers=auth["tecnico"], json={}).status_code == 422
    assert client.patch(f"{url}/{a['id']}", headers=auth["tecnico"], json={"concluida": True}).status_code == 422
    assert client.delete(f"{url}/{b['id']}", headers=auth["tecnico"]).status_code == 422
    removida = client.delete(f"{url}/{b['id']}", headers=auth["tecnico"], params={"motivo": "Etapa duplicada no planejamento"})
    assert removida.status_code == 204, removida.text
    etapas = client.get(url, headers=auth["cliente"]).json()
    assert len(etapas) == 1 and etapas[0]["ordem"] == 1
    logs = db.scalars(select(AuditoriaLog).where(AuditoriaLog.pedido_id == UUID(demanda_id))).all()
    assert {"EDICAO_ETAPA", "REMOCAO_ETAPA"} <= {l.acao for l in logs}


def test_etapa_de_outra_demanda_e_bloqueada(client, auth, demanda_id):
    outra = criar(client, auth)
    etapa = client.post(f"/demandas/{outra}/etapas", headers=auth["admin"], json={"descricao": "Etapa separada"}).json()
    url = f"/demandas/{demanda_id}/etapas/{etapa['id']}"
    assert client.patch(url, headers=auth["admin"], json={"ordem": 1}).status_code == 404
    assert client.delete(url, headers=auth["admin"], params={"motivo": "Nao pode remover outra demanda"}).status_code == 404


def test_etapa_concluida_e_homologacao_preservadas(client, auth, demanda_id):
    base = f"/demandas/{demanda_id}"
    client.post(base + "/status", headers=auth["tecnico"], json={"status": "EXECUCAO"})
    etapa = client.post(base + "/etapas", headers=auth["tecnico"], json={"descricao": "Etapa final"}).json()
    url = base + f"/etapas/{etapa['id']}"
    assert client.post(url + "/conclusao", headers=auth["tecnico"]).status_code == 200
    assert client.patch(url, headers=auth["tecnico"], json={"descricao": "Alteracao indevida"}).status_code == 409
    assert client.delete(url, headers=auth["admin"], params={"motivo": "Nao pode apagar o trabalho concluido"}).status_code == 409
    assert client.post(base + "/status", headers=auth["tecnico"], json={"status": "HOMOLOGACAO"}).status_code == 200
    assert client.patch(url, headers=auth["admin"], json={"ordem": 1}).status_code == 409


def test_remover_ultima_etapa_nao_libera_homologacao(client, auth, demanda_id):
    base = f"/demandas/{demanda_id}"
    client.post(base + "/status", headers=auth["tecnico"], json={"status": "EXECUCAO"})
    etapa = client.post(base + "/etapas", headers=auth["tecnico"], json={"descricao": "Etapa temporaria"}).json()
    assert client.delete(base + f"/etapas/{etapa['id']}", headers=auth["tecnico"], params={"motivo": "Removida por duplicidade"}).status_code == 204
    assert client.post(base + "/status", headers=auth["tecnico"], json={"status": "HOMOLOGACAO"}).status_code == 409


def test_anexos_autorizados_e_link_temporario(client, auth, demanda_id):
    base = f"/demandas/{demanda_id}"
    assert client.get(base + "/anexos", headers=auth["cliente"]).json() == []
    upload = client.post(base + "/evidencias", headers=auth["cliente"],
                         files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/pdf")})
    assert upload.status_code == 201, upload.text
    lista = client.get(base + "/anexos", headers=auth["tecnico"]).json()
    assert len(lista) == 1
    assert "caminho_storage" not in lista[0]
    link = lista[0]["referencia_acesso"]
    assert client.get(link).status_code == 401
    assert client.get(link, headers=auth["outro_cliente"]).status_code == 404
    resposta = client.get(link, headers=auth["cliente"])
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.json()["validade_segundos"] == 300
    assert "token=temporario" in resposta.json()["url"]
    assert client.get(base + "/anexos", headers=auth["outro_cliente"]).status_code == 404
    assert client.get(base + f"/anexos/{uuid4()}/acesso", headers=auth["admin"]).status_code == 404
    outra = criar(client, auth)
    assert client.get(f"/demandas/{outra}/anexos/{lista[0]['id']}/acesso", headers=auth["cliente"]).status_code == 404


def test_erros_storage_nao_expoem_credenciais(client, auth, demanda_id, storage, monkeypatch):
    upload = client.post(f"/demandas/{demanda_id}/evidencias", headers=auth["cliente"],
                         files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/pdf")}).json()
    def falhar(*args, **kwargs):
        raise RuntimeError("chave-privada-do-servidor")
    monkeypatch.setattr(storage, "create_signed_url", falhar)
    resposta = client.get(f"/demandas/{demanda_id}/anexos/{upload['id']}/acesso", headers=auth["cliente"])
    assert resposta.status_code == 503
    assert "chave-privada" not in resposta.text


def test_novas_rotas_exigem_autenticacao(client):
    uid = uuid4()
    assert client.get("/demandas/indicadores").status_code == 401
    assert client.get(f"/demandas/{uid}/anexos").status_code == 401
    assert client.patch(f"/demandas/{uid}/etapas/{uid}", json={"ordem": 1}).status_code == 401


def test_reatribuicao_revoga_novas_leituras_de_anexos(client, auth, demanda_id, criar_usuario):
    base = f"/demandas/{demanda_id}"
    upload = client.post(base + "/evidencias", headers=auth["cliente"],
                         files={"arquivo": ("laudo.pdf", amostras.pdf(), "application/pdf")}).json()
    novo = criar_usuario(PerfilEnum.TECNICO)
    resposta = client.put(base + "/responsavel", headers=auth["admin"],
                           json={"responsavel_id": str(novo.id), "motivo": "Troca de responsavel para nova equipe"})
    assert resposta.status_code == 200, resposta.text
    assert client.get(base + "/anexos", headers=auth["tecnico"]).status_code == 404
    assert client.get(base + f"/anexos/{upload['id']}/acesso", headers=auth["tecnico"]).status_code == 404


def test_falha_de_auditoria_reverte_edicao_de_etapa(client, auth, demanda_id, monkeypatch):
    base = f"/demandas/{demanda_id}/etapas"
    etapa = client.post(base, headers=auth["tecnico"], json={"descricao": "Descricao original"}).json()
    def falhar(*args, **kwargs):
        raise RuntimeError("Auditoria indisponivel")
    monkeypatch.setattr(DemandService, "_auditar", falhar)
    with pytest.raises(RuntimeError, match="Auditoria indisponivel"):
        client.patch(base + f"/{etapa['id']}", headers=auth["tecnico"], json={"descricao": "Nao deve persistir"})
    assert client.get(base, headers=auth["cliente"]).json()[0]["descricao"] == "Descricao original"
