"""Politica central de autorizacao por perfil e vinculo (SCRUM-95)."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AcessoNegadoException
from app.domain.models.enums import PerfilEnum
from app.domain.regras import autorizacao


def _usuario(perfil, ativo=True):
    return SimpleNamespace(id=uuid4(), perfil=perfil, ativo=ativo)


@pytest.fixture
def atores():
    return {
        "admin": _usuario(PerfilEnum.ADMIN),
        "cliente": _usuario(PerfilEnum.CLIENTE),
        "outro_cliente": _usuario(PerfilEnum.CLIENTE),
        "tecnico": _usuario(PerfilEnum.TECNICO),
        "outro_tecnico": _usuario(PerfilEnum.TECNICO),
    }


@pytest.fixture
def pedido(atores):
    return SimpleNamespace(cliente_id=atores["cliente"].id, responsavel_id=atores["tecnico"].id)


def test_escopo_de_leitura_por_perfil(atores):
    assert autorizacao.escopo_leitura(atores["admin"]) == {}
    assert autorizacao.escopo_leitura(atores["cliente"]) == {"cliente_id": atores["cliente"].id}
    assert autorizacao.escopo_leitura(atores["tecnico"]) == {"responsavel_id": atores["tecnico"].id}
    with pytest.raises(AcessoNegadoException):
        autorizacao.escopo_leitura(_usuario("DESCONHECIDO"))


@pytest.mark.parametrize("ator, visivel", [
    ("admin", True), ("cliente", True), ("tecnico", True), ("outro_cliente", False), ("outro_tecnico", False),
])
def test_vinculo_com_a_demanda_define_visibilidade(atores, pedido, ator, visivel):
    assert autorizacao.pode_ver(atores[ator], pedido) is visivel


def test_cliente_nao_vira_responsavel_mesmo_com_o_mesmo_id(atores):
    # O vinculo exige o perfil certo, nao so o UUID: um cliente cujo id coincida
    # com responsavel_id nao ganha poderes operacionais.
    cliente = atores["cliente"]
    pedido = SimpleNamespace(cliente_id=uuid4(), responsavel_id=cliente.id)
    assert not autorizacao.is_responsavel(cliente, pedido)
    with pytest.raises(AcessoNegadoException):
        autorizacao.exigir_equipe_operacional(cliente, pedido)


@pytest.mark.parametrize("ator, permitido", [
    ("admin", True), ("tecnico", True), ("cliente", False), ("outro_tecnico", False),
])
def test_equipe_operacional(atores, pedido, ator, permitido):
    if permitido:
        autorizacao.exigir_equipe_operacional(atores[ator], pedido)
    else:
        with pytest.raises(AcessoNegadoException):
            autorizacao.exigir_equipe_operacional(atores[ator], pedido)


@pytest.mark.parametrize("ator, permitido", [
    ("admin", True), ("cliente", True), ("tecnico", False), ("outro_cliente", False),
])
def test_dono_ou_admin(atores, pedido, ator, permitido):
    if permitido:
        autorizacao.exigir_dono_ou_admin(atores[ator], pedido, "edita-la")
    else:
        with pytest.raises(AcessoNegadoException):
            autorizacao.exigir_dono_ou_admin(atores[ator], pedido, "edita-la")


def test_exigir_perfil_recusa_usuario_inativo_mesmo_com_perfil_certo():
    with pytest.raises(AcessoNegadoException):
        autorizacao.exigir_perfil(_usuario(PerfilEnum.ADMIN, ativo=False), PerfilEnum.ADMIN)
    with pytest.raises(AcessoNegadoException):
        autorizacao.exigir_perfil(_usuario(PerfilEnum.CLIENTE), PerfilEnum.ADMIN)
    autorizacao.exigir_perfil(_usuario(PerfilEnum.ADMIN), PerfilEnum.ADMIN)
