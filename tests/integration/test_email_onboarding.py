"""End-to-end tests for email confirmation, password reset and DEV approval."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import OperacaoConflitanteException
from app.core.security import verify_password
from app.domain.models.contratacao import Contratacao
from app.domain.models.enums import PerfilEnum
from app.domain.models.token_conta import TokenConta
from app.domain.models.user import User
from app.services.cadastro_publico_service import CadastroPublicoService, TERMOS_USO_VERSAO
from app.services.comercial_service import ComercialService
from app.services.tokens_conta_service import TokenInvalido, TokensContaService, digerir


class FakeSender:
    def __init__(self):
        self.sent = []

    def send_token(self, *, email, token, purpose):
        self.sent.append((email, token, purpose))


def test_cadastro_verificacao_e_aprovacao_dev(db, criar_usuario):
    sender = FakeSender()
    # ADMIN persistido antes dos testes de rollback para nao perder sua FK.
    admin = criar_usuario(PerfilEnum.ADMIN)
    email = f"novo-{uuid4().hex}@example.com"
    CadastroPublicoService(db, sender).solicitar(
        nome="Novo cliente", email=email, senha="SenhaForte123", termos_versao=TERMOS_USO_VERSAO
    )
    novo = db.scalar(select(User).where(User.email == email))
    assert novo and novo.situacao_cadastro == "PENDENTE"
    assert novo.origem_cadastro == "PUBLICO"
    assert novo.email_verificado_em is None
    assert novo.termos_uso_versao == TERMOS_USO_VERSAO
    assert novo.termos_uso_aceitos_em is not None
    assert novo.termos_uso_aceitos_em.utcoffset() == timedelta(0)
    assert admin.termos_uso_aceitos_em is None
    assert len(sender.sent) == 1
    _, token, purpose = sender.sent[0]
    assert purpose == "VERIFICAR_EMAIL"
    registrado = db.scalar(select(TokenConta).where(TokenConta.usuario_id == novo.id))
    assert registrado.token_hash == digerir(token)
    assert token not in registrado.token_hash
    assert db.scalar(select(Contratacao).where(
        Contratacao.usuario_cliente_id == novo.id
    )) is None

    with pytest.raises(OperacaoConflitanteException, match="e-mail"):
        ComercialService(db).aprovar_conta_dev(admin, usuario_id=novo.id)
    TokensContaService(db).confirmar_email(token)
    assert novo.email_verificado_em is not None
    assert novo.situacao_cadastro == "PENDENTE"
    with pytest.raises(TokenInvalido):
        TokensContaService(db).confirmar_email(token)
    approved = ComercialService(db).aprovar_conta_dev(admin, usuario_id=novo.id)
    assert approved.situacao == "ATIVA" and approved.tipo == "DEV"
    assert novo.situacao_cadastro == "ATIVO"


def test_redefinicao_replay_e_expiracao(db, criar_usuario):
    sender = FakeSender()
    user = criar_usuario(PerfilEnum.CLIENTE)
    CadastroPublicoService(db, sender).solicitar_reset(email=user.email)
    assert len(sender.sent) == 1
    _, token, purpose = sender.sent[0]
    assert purpose == "REDEFINIR_SENHA"
    TokensContaService(db).redefinir_senha(token, "NovaSenha456")
    assert verify_password("NovaSenha456", user.senha_hash)
    with pytest.raises(TokenInvalido):
        TokensContaService(db).redefinir_senha(token, "Repetir1234")

    vencido = "token-com-mais-de-vinte-caracteres-falso-123"
    db.add(TokenConta(
        usuario_id=user.id, token_hash=digerir(vencido),
        finalidade="REDEFINIR_SENHA",
        expira_em=datetime.now(timezone.utc) - timedelta(seconds=2),
    ))
    db.flush()
    with pytest.raises(TokenInvalido):
        TokensContaService(db).redefinir_senha(vencido, "OutraSenha456")
    assert verify_password("NovaSenha456", user.senha_hash)
