"""Cadastro publico: nova identidade sem privilegios e link de verificacao."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User
from app.services.email_sender import EmailSender
from app.services.tokens_conta_service import TokensContaService


# Deve corresponder ao documento exibido no cadastro do frontend.
TERMOS_USO_VERSAO = "1.1"


class CadastroPublicoService:
    def __init__(self, db: Session, sender: EmailSender):
        self.db = db
        self.sender = sender

    def solicitar(
        self, *, nome: str, email: str, senha: str, termos_versao: str
    ) -> None:
        hashed = hash_password(senha)
        try:
            # Nao divulgar se o e-mail ja existe.
            existente = self.db.scalar(select(User.id).where(func.lower(User.email) == email))
            if existente is not None:
                return
            user = User(
                nome=nome, email=email, senha_hash=hashed,
                perfil=PerfilEnum.CLIENTE, origem_cadastro="PUBLICO",
                situacao_cadastro="PENDENTE", ativo=True,
                termos_uso_versao=termos_versao,
                termos_uso_aceitos_em=datetime.now(timezone.utc),
            )
            self.db.add(user)
            self.db.flush()
            token = TokensContaService(self.db).emitir(user, "VERIFICAR_EMAIL")
            if not token:
                raise RuntimeError("Token de verificacao nao emitido.")
            # Sem entrega de email, a conta nao fica criada silenciosamente.
            self.sender.send_token(email=email, token=token, purpose="VERIFICAR_EMAIL")
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
        except Exception:
            self.db.rollback()
            raise

    def reenviar(self, *, email: str) -> None:
        try:
            user = self.db.scalar(select(User).where(func.lower(User.email) == email))
            if user is None or user.email_verificado_em is not None or user.origem_cadastro != "PUBLICO":
                return
            token = TokensContaService(self.db).emitir(user, "VERIFICAR_EMAIL")
            if not token:
                return
            self.sender.send_token(email=email, token=token, purpose="VERIFICAR_EMAIL")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def solicitar_reset(self, *, email: str) -> None:
        try:
            user = self.db.scalar(select(User).where(func.lower(User.email) == email))
            if user is None or user.ativo is not True:
                return
            token = TokensContaService(self.db).emitir(user, "REDEFINIR_SENHA")
            if not token:
                return
            self.sender.send_token(email=email, token=token, purpose="REDEFINIR_SENHA")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
