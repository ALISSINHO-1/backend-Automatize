"""Gestao de usuarios e perfis pelo ADMIN (SCRUM-96 / SCRUM-99).

Regras que protegem a consistencia do sistema:
- O ADMIN nao altera o proprio perfil nem a propria conta: evita ficar sem acesso por engano.
- Sempre resta ao menos um ADMIN ativo.
- Tecnico com demanda em aberto sob sua responsabilidade nao e inativado nem
  muda de perfil: a demanda ficaria sem ninguem para executa-la. Reatribua antes.
- Cliente com demandas nao muda de perfil: pedido.cliente_id passaria a apontar
  para quem nao e cliente. Inativar e permitido (bloqueia o login, preserva o historico).
Toda alteracao fica na auditoria (sem pedido vinculado).
"""
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.core.exceptions import (
    AcessoNegadoException,
    OperacaoConflitanteException,
    RecursoNaoEncontradoException,
    RegraNegocioException,
)
from app.core.security import hash_password, password_exceeds_bcrypt_limit
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.domain.regras import autorizacao, ciclo_vida


TAMANHO_MINIMO_SENHA = 8


class UsuarioAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def listar(
        self,
        admin: User,
        *,
        perfil: PerfilEnum | None = None,
        ativo: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[User]:
        autorizacao.exigir_perfil(admin, PerfilEnum.ADMIN)
        consulta = select(User)
        if perfil is not None:
            consulta = consulta.where(User.perfil == perfil)
        if ativo is not None:
            consulta = consulta.where(User.ativo.is_(ativo))
        return self.db.scalars(consulta.order_by(User.nome, User.id).offset(offset).limit(limit)).all()

    def criar(self, admin: User, *, nome: str, email: str, senha: str, perfil: PerfilEnum) -> User:
        autorizacao.exigir_perfil(admin, PerfilEnum.ADMIN)
        nome = ciclo_vida.validar_texto(nome, "nome", 3, 255)
        # O login compara o e-mail exatamente; normalizar aqui evita contas
        # duplicadas que so diferem em maiusculas.
        email = (email or "").strip().lower()
        if len(senha or "") < TAMANHO_MINIMO_SENHA:
            raise RegraNegocioException(f"A senha deve ter no minimo {TAMANHO_MINIMO_SENHA} caracteres.")
        if password_exceeds_bcrypt_limit(senha):
            raise RegraNegocioException("A senha deve ter no maximo 72 bytes.")

        with self._transacao():
            existente = self.db.scalar(select(User.id).where(func.lower(User.email) == email))
            if existente is not None:
                raise OperacaoConflitanteException("Ja existe um usuario com este e-mail.")
            usuario = User(nome=nome, email=email, senha_hash=hash_password(senha), perfil=perfil, ativo=True)
            self.db.add(usuario)
            self.db.flush()
            self._auditar(admin, "CRIACAO_USUARIO", {
                "usuario_id": str(usuario.id),
                "perfil": perfil.value,
            })
        return usuario

    def alterar_perfil(self, admin: User, usuario_id: UUID, *, perfil: PerfilEnum) -> User:
        autorizacao.exigir_perfil(admin, PerfilEnum.ADMIN)
        with self._transacao():
            alvo = self._obter_para_alterar(admin, usuario_id)
            if alvo.perfil == perfil:
                raise OperacaoConflitanteException(f"O usuario ja tem o perfil {perfil.value}.")
            self._exigir_outro_admin_ativo(alvo, "alterar o perfil do")
            self._exigir_tecnico_sem_demandas_abertas(alvo, "alterar o perfil")
            if alvo.perfil == PerfilEnum.CLIENTE and self._possui_demandas_como_cliente(alvo.id):
                raise OperacaoConflitanteException(
                    "Este cliente possui demandas e nao pode mudar de perfil. Inative a conta, se necessario."
                )

            anterior = alvo.perfil
            alvo.perfil = perfil
            self._auditar(admin, "ALTERACAO_PERFIL_USUARIO", {
                "usuario_id": str(alvo.id),
                "perfil_anterior": anterior.value,
                "perfil_novo": perfil.value,
            })
        return alvo

    def alterar_ativo(self, admin: User, usuario_id: UUID, *, ativo: bool) -> User:
        autorizacao.exigir_perfil(admin, PerfilEnum.ADMIN)
        with self._transacao():
            alvo = self._obter_para_alterar(admin, usuario_id)
            if (alvo.ativo is True) == ativo:
                raise OperacaoConflitanteException(
                    "O usuario ja esta ativo." if ativo else "O usuario ja esta inativo."
                )
            if not ativo:
                self._exigir_outro_admin_ativo(alvo, "inativar o")
                self._exigir_tecnico_sem_demandas_abertas(alvo, "inativar")

            alvo.ativo = ativo
            self._auditar(admin, "ATIVACAO_USUARIO" if ativo else "INATIVACAO_USUARIO", {
                "usuario_id": str(alvo.id),
            })
        return alvo

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------

    @contextmanager
    def _transacao(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _obter_para_alterar(self, admin: User, usuario_id: UUID) -> User:
        if usuario_id == admin.id:
            raise AcessoNegadoException("O ADMIN nao pode alterar o perfil ou o status da propria conta.")
        # Bloqueia a linha: duas alteracoes simultaneas nao podem, juntas,
        # deixar o sistema sem ADMIN ativo.
        alvo = self.db.scalar(
            select(User).where(User.id == usuario_id).with_for_update().execution_options(populate_existing=True)
        )
        if alvo is None:
            raise RecursoNaoEncontradoException("Usuario nao encontrado.")
        return alvo

    def _exigir_outro_admin_ativo(self, alvo: User, operacao: str) -> None:
        if alvo.perfil != PerfilEnum.ADMIN or alvo.ativo is not True:
            return
        admins = self.db.scalars(
            select(User.id).where(User.perfil == PerfilEnum.ADMIN, User.ativo.is_(True)).with_for_update()
        ).all()
        if len(admins) <= 1:
            raise OperacaoConflitanteException(f"Nao e possivel {operacao} ultimo ADMIN ativo.")

    def _exigir_tecnico_sem_demandas_abertas(self, alvo: User, operacao: str) -> None:
        if alvo.perfil != PerfilEnum.TECNICO:
            return
        abertas = self.db.scalar(
            select(func.count()).select_from(Pedido).where(
                Pedido.responsavel_id == alvo.id,
                Pedido.status != StatusPedidoEnum.CONCLUIDO,
            )
        ) or 0
        if abertas:
            raise OperacaoConflitanteException(
                f"Nao e possivel {operacao} este tecnico: ele e responsavel por {abertas} demanda(s) "
                "em aberto. Reatribua-as antes."
            )

    def _possui_demandas_como_cliente(self, usuario_id: UUID) -> bool:
        return self.db.scalar(select(Pedido.id).where(Pedido.cliente_id == usuario_id).limit(1)) is not None

    def _auditar(self, admin: User, acao: str, detalhes: dict[str, Any]) -> None:
        self.db.add(AuditoriaLog(
            usuario_id=admin.id,
            pedido_id=None,
            acao=acao,
            detalhes=detalhes,
            created_at=datetime.now(timezone.utc),
        ))
        self.db.flush()
