"""These tests run only with TEST_DATABASE_URL on isolated PostgreSQL."""
from uuid import uuid4

from sqlalchemy import select

from app.api.v1.endpoints.contexto import meu_contexto
from app.domain.models.contratacao import Contratacao
from app.domain.models.enums import PerfilEnum
from app.domain.models.organizacao import Organizacao
from app.domain.models.organizacao_usuario import OrganizacaoUsuario
from app.domain.models.user import User
from app.services.cadastro_publico_service import CadastroPublicoService


def test_public_signup_creates_pending_without_contract(db):
    email = f"contato-{uuid4().hex}@example.com"
    service = CadastroPublicoService(db)
    service.solicitar(nome="Empresa Interessada", email=email, senha="SenhaSegura123")
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.perfil == PerfilEnum.CLIENTE
    assert user.situacao_cadastro == "PENDENTE"
    assert user.ativo is True
    assert user.senha_hash != "SenhaSegura123"
    assert db.scalar(
        select(Contratacao.id).where(Contratacao.usuario_cliente_id == user.id)
    ) is None
    service.solicitar(nome="Outra Pessoa", email=email, senha="OutraSenha123")
    assert db.scalar(select(User).where(User.email == email)).id == user.id


def test_context_does_not_cross_tenants(db, criar_usuario):
    a, b = criar_usuario(PerfilEnum.CLIENTE), criar_usuario(PerfilEnum.CLIENTE)
    org_a = Organizacao(nome="Empresa Alfa", criado_por_id=a.id)
    org_b = Organizacao(nome="Empresa Beta", criado_por_id=b.id)
    db.add_all([org_a, org_b])
    db.flush()
    db.add_all([
        OrganizacaoUsuario(organizacao_id=org_a.id, usuario_id=a.id, papel="GESTOR"),
        OrganizacaoUsuario(organizacao_id=org_b.id, usuario_id=b.id, papel="GESTOR"),
        Contratacao(tipo="DEV", situacao="ATIVA", usuario_cliente_id=a.id),
        Contratacao(tipo="DEV", situacao="ATIVA", usuario_cliente_id=b.id),
        Contratacao(tipo="SAAS", situacao="ATIVA", organizacao_id=org_a.id),
        Contratacao(tipo="SAAS", situacao="ATIVA", organizacao_id=org_b.id),
    ])
    db.flush()
    ca = meu_contexto(usuario=a, db=db)
    cb = meu_contexto(usuario=b, db=db)
    assert {(e.tipo, e.organizacao_id) for e in ca.ambientes} == {
        ("DEV", None), ("SAAS", org_a.id)
    }
    assert {(e.tipo, e.organizacao_id) for e in cb.ambientes} == {
        ("DEV", None), ("SAAS", org_b.id)
    }
    a.situacao_cadastro = "PENDENTE"
    assert meu_contexto(usuario=a, db=db).ambientes == []
