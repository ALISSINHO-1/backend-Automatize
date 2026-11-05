"""Regras administrativas com JWT real e PostgreSQL real:
usuarios e perfis (SCRUM-96/99), atribuicao (SCRUM-97) e ocorrencias (SCRUM-98)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select # type: ignore

from app.core.exceptions import OperacaoConflitanteException

from app.domain.models import AuditoriaLog
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User
from app.services.usuario_admin_service import UsuarioAdminService
from tests.integration.test_demandas_acoes_api import (  # noqa: F401
    _homologar, atores, auth, client, demanda_id, settings,
)


def _confirmar(db):
    # Os services fazem rollback quando recusam algo; sem um commit antes, esse
    # rollback descartaria tambem os usuarios criados pelo proprio teste.
    db.commit()


def _token_de(client, usuario_id, settings):
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(str(usuario_id), settings)}"}


def _para_execucao_com_etapa_concluida(client, auth, demanda_id):
    assert client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                       json={"status": "EXECUCAO"}).status_code == 200
    etapa = client.post(f"/demandas/{demanda_id}/etapas", headers=auth["tecnico"], json={"descricao": "Executar"})
    assert client.post(f"/demandas/{demanda_id}/etapas/{etapa.json()['id']}/conclusao",
                       headers=auth["tecnico"]).status_code == 200


# ----------------------------------------------------------------------
# Usuarios e perfis (SCRUM-96 / SCRUM-99)
# ----------------------------------------------------------------------

NOVO_USUARIO = {"nome": "Tecnica Nova", "email": "  Tecnica.Nova@Example.com ", "senha": "senha-forte-1",
                "perfil": "TECNICO"}


def test_somente_admin_gerencia_usuarios(client, db, auth, atores):
    _confirmar(db)
    alvo = atores["outro_cliente"].id
    for perfil in ("cliente", "tecnico"):
        assert client.get("/usuarios", headers=auth[perfil]).status_code == 403
        assert client.post("/usuarios", headers=auth[perfil], json=NOVO_USUARIO).status_code == 403
        assert client.patch(f"/usuarios/{alvo}/ativo", headers=auth[perfil], json={"ativo": False}).status_code == 403
        assert client.patch(f"/usuarios/{alvo}/perfil", headers=auth[perfil],
                            json={"perfil": "ADMIN"}).status_code == 403
    assert client.get("/usuarios").status_code == 401


def test_admin_lista_com_filtros_e_sem_dados_sensiveis(client, auth, atores):
    resposta = client.get("/usuarios", headers=auth["admin"], params={"perfil": "TECNICO", "ativo": True})
    assert resposta.status_code == 200
    linhas = resposta.json()
    assert str(atores["tecnico"].id) in {linha["id"] for linha in linhas}
    assert {linha["perfil"] for linha in linhas} == {"TECNICO"}
    assert all("senha_hash" not in linha and "senha" not in linha for linha in linhas)


def test_admin_cria_usuario_que_consegue_logar(client, db, auth, atores):
    resposta = client.post("/usuarios", headers=auth["admin"], json=NOVO_USUARIO)
    assert resposta.status_code == 201, resposta.text
    criado = resposta.json()
    assert criado["email"] == "tecnica.nova@example.com"
    assert (criado["perfil"], criado["ativo"]) == ("TECNICO", True)

    login = client.post("/auth/login", json={"email": "tecnica.nova@example.com", "senha": "senha-forte-1"})
    assert login.status_code == 200, login.text

    duplicado = client.post("/usuarios", headers=auth["admin"],
                            json=NOVO_USUARIO | {"email": "TECNICA.NOVA@example.com"})
    assert duplicado.status_code == 409

    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "CRIACAO_USUARIO"))
    assert log.usuario_id == atores["admin"].id
    assert log.detalhes == {"usuario_id": criado["id"], "perfil": "TECNICO"}


@pytest.mark.parametrize("corpo, codigo", [
    (NOVO_USUARIO | {"senha": "curta"}, 422),
    (NOVO_USUARIO | {"email": "sem-arroba"}, 422),
    (NOVO_USUARIO | {"perfil": "SUPERUSUARIO"}, 422),
    (NOVO_USUARIO | {"ativo": False}, 422),
])
def test_criacao_valida_os_dados(client, db, auth, corpo, codigo):
    _confirmar(db)
    assert client.post("/usuarios", headers=auth["admin"], json=corpo).status_code == codigo


def test_usuario_inativado_perde_o_acesso_e_pode_ser_reativado(client, db, auth, atores, settings):
    _confirmar(db)
    cliente = atores["outro_cliente"]
    token = _token_de(client, cliente.id, settings)
    assert client.get("/auth/me", headers=token).status_code == 200

    resposta = client.patch(f"/usuarios/{cliente.id}/ativo", headers=auth["admin"], json={"ativo": False})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["ativo"] is False
    assert client.get("/auth/me", headers=token).status_code == 401
    assert client.patch(f"/usuarios/{cliente.id}/ativo", headers=auth["admin"],
                        json={"ativo": False}).status_code == 409

    assert client.patch(f"/usuarios/{cliente.id}/ativo", headers=auth["admin"],
                        json={"ativo": True}).status_code == 200
    assert client.get("/auth/me", headers=token).status_code == 200
    acoes = db.scalars(select(AuditoriaLog.acao).where(AuditoriaLog.acao.in_(
        ["INATIVACAO_USUARIO", "ATIVACAO_USUARIO"]))).all()
    assert sorted(acoes) == ["ATIVACAO_USUARIO", "INATIVACAO_USUARIO"]


def test_admin_nao_altera_a_propria_conta(client, db, auth, atores):
    _confirmar(db)
    admin = atores["admin"].id
    assert client.patch(f"/usuarios/{admin}/ativo", headers=auth["admin"], json={"ativo": False}).status_code == 403
    assert client.patch(f"/usuarios/{admin}/perfil", headers=auth["admin"],
                        json={"perfil": "TECNICO"}).status_code == 403


def test_ultimo_admin_ativo_e_preservado_mesmo_em_corrida(client, db, auth, atores, criar_usuario):
    # Pela API um ADMIN nao altera a si mesmo, entao o unico jeito de zerar os
    # ADMINs e dois rebaixarem um ao outro ao mesmo tempo. Simula o segundo
    # pedido com a visao "velha" de quem ja foi rebaixado.
    for outro in db.scalars(select(User).where(User.perfil == PerfilEnum.ADMIN, User.id != atores["admin"].id)):
        outro.ativo = False
    segundo = criar_usuario(PerfilEnum.ADMIN)
    assert client.patch(f"/usuarios/{segundo.id}/perfil", headers=auth["admin"],
                        json={"perfil": "TECNICO"}).status_code == 200

    visao_antiga = SimpleNamespace(id=segundo.id, perfil=PerfilEnum.ADMIN, ativo=True)
    service = UsuarioAdminService(db)
    with pytest.raises(OperacaoConflitanteException, match="ultimo ADMIN ativo"):
        service.alterar_perfil(visao_antiga, atores["admin"].id, perfil=PerfilEnum.TECNICO)
    with pytest.raises(OperacaoConflitanteException, match="ultimo ADMIN ativo"):
        service.alterar_ativo(visao_antiga, atores["admin"].id, ativo=False)


def test_tecnico_com_demanda_aberta_nao_e_inativado_nem_muda_de_perfil(client, auth, atores, demanda_id):
    tecnico = atores["tecnico"].id
    resposta = client.patch(f"/usuarios/{tecnico}/ativo", headers=auth["admin"], json={"ativo": False})
    assert resposta.status_code == 409
    assert "Reatribua" in resposta.json()["detail"]
    assert client.patch(f"/usuarios/{tecnico}/perfil", headers=auth["admin"],
                        json={"perfil": "CLIENTE"}).status_code == 409


def test_cliente_com_demandas_nao_muda_de_perfil_mas_pode_ser_inativado(client, auth, atores, demanda_id):
    cliente = atores["cliente"].id
    assert client.patch(f"/usuarios/{cliente}/perfil", headers=auth["admin"],
                        json={"perfil": "TECNICO"}).status_code == 409
    assert client.patch(f"/usuarios/{cliente}/ativo", headers=auth["admin"], json={"ativo": False}).status_code == 200


def test_usuario_inexistente(client, db, auth):
    from uuid import uuid4

    _confirmar(db)

    assert client.patch(f"/usuarios/{uuid4()}/ativo", headers=auth["admin"], json={"ativo": False}).status_code == 404


# ----------------------------------------------------------------------
# Atribuicao e reatribuicao (SCRUM-97)
# ----------------------------------------------------------------------

def test_reatribuicao_exige_motivo_e_tecnico_diferente(client, db, auth, atores, demanda_id, criar_usuario):
    novo = criar_usuario(PerfilEnum.TECNICO)
    _confirmar(db)
    url = f"/demandas/{demanda_id}/responsavel"

    mesmo = client.put(url, headers=auth["admin"], json={"responsavel_id": str(atores["tecnico"].id)})
    assert mesmo.status_code == 409
    assert client.put(url, headers=auth["admin"], json={"responsavel_id": str(novo.id)}).status_code == 422
    assert client.put(url, headers=auth["admin"],
                      json={"responsavel_id": str(novo.id), "motivo": "curto"}).status_code == 422

    resposta = client.put(url, headers=auth["admin"],
                          json={"responsavel_id": str(novo.id), "motivo": "Tecnico anterior de licenca"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["responsavel_id"] == str(novo.id)

    log = db.scalars(select(AuditoriaLog).where(AuditoriaLog.acao == "ATRIBUICAO_RESPONSAVEL")
                     .order_by(AuditoriaLog.created_at)).all()[-1]
    assert log.detalhes["motivo"] == "Tecnico anterior de licenca"
    # O tecnico anterior perde o acesso a demanda junto com a responsabilidade.
    assert client.get(f"/demandas/{demanda_id}", headers=auth["tecnico"]).status_code == 404


def test_atribuicao_recusa_tecnico_inativo_e_quem_nao_e_tecnico(client, db, auth, atores, demanda_id,
                                                                  criar_usuario):
    inativo = criar_usuario(PerfilEnum.TECNICO, ativo=False)
    _confirmar(db)
    url = f"/demandas/{demanda_id}/responsavel"
    motivo = "Troca de tecnico solicitada"
    assert client.put(url, headers=auth["admin"],
                      json={"responsavel_id": str(inativo.id), "motivo": motivo}).status_code == 404
    assert client.put(url, headers=auth["admin"],
                      json={"responsavel_id": str(atores["cliente"].id), "motivo": motivo}).status_code == 404
    assert client.put(url, headers=auth["tecnico"],
                      json={"responsavel_id": str(atores["tecnico"].id)}).status_code == 403


# ----------------------------------------------------------------------
# Ocorrencias e correcoes (SCRUM-98)
# ----------------------------------------------------------------------

ERRO = {"tipo": "ERRO", "descricao": "Tela de login nao abre no celular"}
CORRECAO = {"descricao_resolucao": "Ajustado o layout responsivo do login"}


def test_ciclo_de_ocorrencia_bloqueia_homologacao_ate_a_correcao(client, db, auth, demanda_id):
    _para_execucao_com_etapa_concluida(client, auth, demanda_id)

    aberta = client.post(f"/demandas/{demanda_id}/ocorrencias", headers=auth["cliente"], json=ERRO)
    assert aberta.status_code == 201, aberta.text
    assert aberta.json()["resolvida"] is False

    bloqueada = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                            json={"status": "HOMOLOGACAO"})
    assert bloqueada.status_code == 409
    assert "ocorrencias em aberto" in bloqueada.json()["detail"]

    url_resolucao = f"/demandas/{demanda_id}/ocorrencias/{aberta.json()['id']}/resolucao"
    assert client.post(url_resolucao, headers=auth["cliente"], json=CORRECAO).status_code == 403
    resolvida = client.post(url_resolucao, headers=auth["tecnico"], json=CORRECAO)
    assert resolvida.status_code == 200, resolvida.text
    assert resolvida.json()["resolvida"] is True
    assert resolvida.json()["descricao_resolucao"] == CORRECAO["descricao_resolucao"]
    assert client.post(url_resolucao, headers=auth["tecnico"], json=CORRECAO).status_code == 409

    assert client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                       json={"status": "HOMOLOGACAO"}).status_code == 200
    acoes = db.scalars(select(AuditoriaLog.acao).where(
        AuditoriaLog.acao.in_(["REGISTRO_OCORRENCIA", "RESOLUCAO_OCORRENCIA"]))).all()
    assert sorted(acoes) == ["REGISTRO_OCORRENCIA", "RESOLUCAO_OCORRENCIA"]


def test_regras_de_registro_de_ocorrencia(client, auth, atores, demanda_id):
    url = f"/demandas/{demanda_id}/ocorrencias"
    assert client.post(url, headers=auth["cliente"],
                       json={"tipo": "REGRESSO_ESTADO", "descricao": "Regresso manual nao vale"}).status_code == 422
    assert client.post(url, headers=auth["cliente"], json={"tipo": "ERRO", "descricao": "curta"}).status_code == 422
    assert client.post(url, headers=auth["outro_cliente"], json=ERRO).status_code == 404
    assert client.post(url, headers=auth["tecnico"],
                       json={"tipo": "SOLICITACAO_CORRECAO", "descricao": "Ajustar texto do rodape"}).status_code == 201
    assert client.post(url, headers=auth["admin"], json=ERRO).status_code == 201

    listagem = client.get(url, headers=auth["cliente"])
    assert listagem.status_code == 200
    assert [o["tipo"] for o in listagem.json()] == ["SOLICITACAO_CORRECAO", "ERRO"]
    assert client.get(url, headers=auth["outro_cliente"]).status_code == 404


def test_em_homologacao_a_correcao_e_pedida_pela_rejeicao(client, auth, demanda_id):
    _homologar(client, auth, demanda_id)
    url = f"/demandas/{demanda_id}/ocorrencias"
    assert client.post(url, headers=auth["cliente"], json=ERRO).status_code == 409

    rejeicao = client.post(f"/demandas/{demanda_id}/rejeicao", headers=auth["cliente"],
                           json={"motivo": "O relatorio final veio sem os graficos"})
    assert rejeicao.status_code == 200, rejeicao.text

    # O regresso gerado pela rejeicao fica aberto e segura a nova homologacao.
    [regresso] = client.get(url, headers=auth["tecnico"]).json()
    assert (regresso["tipo"], regresso["resolvida"]) == ("REGRESSO_ESTADO", False)
    assert client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                       json={"status": "HOMOLOGACAO"}).status_code == 409

    assert client.post(f"{url}/{regresso['id']}/resolucao", headers=auth["tecnico"],
                       json={"descricao_resolucao": "Graficos incluidos no relatorio"}).status_code == 200
    assert client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                       json={"status": "HOMOLOGACAO"}).status_code == 200
