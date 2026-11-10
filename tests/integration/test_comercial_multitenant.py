"""Commercial roles and contract activation on disposable PostgreSQL."""
import pytest

from app.api.v1.endpoints.contexto import meu_contexto
from app.core.exceptions import AcessoNegadoException, OperacaoConflitanteException
from app.domain.models.enums import PerfilEnum
from app.services.comercial_service import ComercialService


def test_admin_creates_company_and_links_local_manager_without_global_admin(db, criar_usuario):
    admin = criar_usuario(PerfilEnum.ADMIN)
    client = criar_usuario(PerfilEnum.CLIENTE)
    service = ComercialService(db)

    with pytest.raises(AcessoNegadoException):
        service.criar_organizacao(client, nome="Empresa Externa")

    org = service.criar_organizacao(admin, nome="Empresa Externa")
    membership = service.vincular_membro(
        admin, organizacao_id=org.id, usuario_id=client.id, papel="GESTOR"
    )
    assert membership.papel == "GESTOR"
    assert client.perfil == PerfilEnum.CLIENTE

    with pytest.raises(OperacaoConflitanteException):
        service.vincular_membro(
            admin, organizacao_id=org.id, usuario_id=client.id, papel="GESTOR"
        )


def test_dev_contract_requires_explicit_admin_activation(db, criar_usuario):
    admin = criar_usuario(PerfilEnum.ADMIN)
    client = criar_usuario(PerfilEnum.CLIENTE)
    service = ComercialService(db)
    contract = service.criar_contrato_dev(admin, usuario_id=client.id)
    assert contract.situacao == "PENDENTE"
    assert not any(a.contratacao_id == contract.id for a in meu_contexto(usuario=client, db=db).ambientes)
    service.ativar_contrato_dev(admin, contrato_id=contract.id)
    assert contract.situacao == "ATIVA"
    assert [a.tipo for a in meu_contexto(usuario=client, db=db).ambientes] == ["DEV"]


def test_saas_contract_does_not_unlock_unimplemented_tenant_api(db, criar_usuario):
    admin = criar_usuario(PerfilEnum.ADMIN)
    client = criar_usuario(PerfilEnum.CLIENTE)
    service = ComercialService(db)
    org = service.criar_organizacao(admin, nome="Outra Empresa")
    service.vincular_membro(
        admin, organizacao_id=org.id, usuario_id=client.id, papel="GESTOR"
    )
    contract = service.criar_contrato_saas(admin, organizacao_id=org.id)
    assert contract.situacao == "PENDENTE"
    # Conta LEGADO pode manter ambiente DEV; o SaaS pendente nao aparece.
    assert not any(a.tipo == "SAAS" for a in meu_contexto(usuario=client, db=db).ambientes)
    with pytest.raises(OperacaoConflitanteException):
        service.ativar_contrato_dev(admin, contrato_id=contract.id)
