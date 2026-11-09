"""Tokens fortes de uso unico, expiracao e bloqueio de reutilizacao."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.models.token_conta import TokenConta
from app.domain.models.user import User


def digerir(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class TokenInvalido(Exception):
    pass


class TokensContaService:
    def __init__(self, db: Session):
        self.db = db

    def emitir(self, user: User, purpose: str) -> str:
        now = datetime.now(timezone.utc)
        if purpose not in ("VERIFICAR_EMAIL", "REDEFINIR_SENHA"):
            raise ValueError("Finalidade invalida.")
        # Cadencia: nao permitir reenvio repetido para mesmo usuario.
        recente = self.db.scalar(
            select(TokenConta.id).where(
                TokenConta.usuario_id == user.id,
                TokenConta.finalidade == purpose,
                TokenConta.criado_em >= now - timedelta(minutes=5),
                TokenConta.usado_em.is_(None),
            ).limit(1)
        )
        if recente is not None:
            return ""
        anteriores = self.db.scalars(
            select(TokenConta).where(
                TokenConta.usuario_id == user.id,
                TokenConta.finalidade == purpose,
                TokenConta.usado_em.is_(None),
            ).with_for_update()
        ).all()
        for item in anteriores:
            item.usado_em = now
        token = token_urlsafe(32)
        self.db.add(TokenConta(
            usuario_id=user.id,
            token_hash=digerir(token),
            finalidade=purpose,
            expira_em=now + timedelta(minutes=30 if purpose == "VERIFICAR_EMAIL" else 15),
        ))
        self.db.flush()
        return token

    def _consumir(self, token: str, purpose: str) -> tuple[User, TokenConta]:
        now = datetime.now(timezone.utc)
        token_row = self.db.scalar(
            select(TokenConta).where(
                TokenConta.token_hash == digerir(token),
                TokenConta.finalidade == purpose,
                TokenConta.usado_em.is_(None),
            ).with_for_update()
        )
        if token_row is None or token_row.expira_em <= now:
            raise TokenInvalido()
        user = self.db.get(User, token_row.usuario_id)
        if user is None or user.ativo is not True:
            raise TokenInvalido()
        token_row.usado_em = now
        return user, token_row

    def confirmar_email(self, token: str) -> None:
        try:
            user, _ = self._consumir(token, "VERIFICAR_EMAIL")
            user.email_verificado_em = datetime.now(timezone.utc)
            # Ainda fica pendente: somente contrato e aprovacao liberam acesso.
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def redefinir_senha(self, token: str, nova_senha: str) -> None:
        try:
            user, _ = self._consumir(token, "REDEFINIR_SENHA")
            user.senha_hash = hash_password(nova_senha)
            user.token_version = (user.token_version or 0) + 1
            # Outros links de reset sao invalidados atomica e imediatamente.
            usados = self.db.scalars(
                select(TokenConta).where(
                    TokenConta.usuario_id == user.id,
                    TokenConta.finalidade == "REDEFINIR_SENHA",
                    TokenConta.usado_em.is_(None),
                ).with_for_update()
            ).all()
            agora = datetime.now(timezone.utc)
            for item in usados:
                item.usado_em = agora
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
