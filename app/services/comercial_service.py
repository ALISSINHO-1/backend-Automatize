"""Operacoes comerciais internas: somente ADMIN, com auditoria em transacao."""
from contextlib import contextmanager
from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    OperacaoConflitanteException, RecursoNaoEncontradoException,
    RegraNegocioException,
)
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.contratacao import Contratacao
from app.domain.models.enums import PerfilEnum
from app.domain.models.organizacao import Organizacao
from app.domain.models.organizacao_usuario import OrganizacaoUsuario
from app.domain.models.user import User
from app.domain.regras import autorizacao


class ComercialService:
    def __init__(self, db: Session):
        self.db = db

    @contextmanager
    def _transacao(self) -> Iterator[None]:
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _auditar(self, admin: User, acao: str, dados: dict) -> None:
        self.db.add(AuditoriaLog(
            usuario_id=admin.id, pedido_id=None, acao=acao, detalhes=dados
        ))
        self.db.flush()

    def _admin(self, usuario: User) -> None:
        autorizacao.exigir_perfil(usuario, PerfilEnum.ADMIN)

    def _cliente_apto(self, usuario_id: UUID) -> User:
        usuario = self.db.get(User, usuario_id)
        if (usuario is None or usuario.perfil != PerfilEnum.CLIENTE
                or usuario.ativo is not True or usuario.situacao_cadastro != "ATIVO"):
            raise RecursoNaoEncontradoException(
                "Cliente inexistente, inativo ou ainda pendente de verificacao."
            )
        return usuario

    def _organizacao_ativa(self, organizacao_id: UUID) -> Organizacao:
        org = self.db.get(Organizacao, organizacao_id)
        if org is None or org.ativa is not True:
            raise RecursoNaoEncontradoException("Organizacao inexistente ou inativa.")
        return org

    def criar_organizacao(self, admin: User, *, nome: str) -> Organizacao:
        self._admin(admin)
        nome = (nome or "").strip()
        if not 3 <= len(nome) <= 255:
            raise RegraNegocioException("O nome da organizacao deve ter de 3 a 255 caracteres.")
        with self._transacao():
            org = Organizacao(nome=nome, criado_por_id=admin.id)
            self.db.add(org)
            self.db.flush()
            self._auditar(admin, "CRIACAO_ORGANIZACAO", {"organizacao_id": str(org.id)})
        return org

    def vincular_membro(
        self, admin: User, *, organizacao_id: UUID, usuario_id: UUID, papel: str,
    ) -> OrganizacaoUsuario:
        self._admin(admin)
        if papel not in ("GESTOR", "COLABORADOR"):
            raise RegraNegocioException("Papel empresarial invalido.")
        with self._transacao():
            self._organizacao_ativa(organizacao_id)
            self._cliente_apto(usuario_id)
            existente = self.db.scalar(
                select(OrganizacaoUsuario.id).where(
                    OrganizacaoUsuario.organizacao_id == organizacao_id,
                    OrganizacaoUsuario.usuario_id == usuario_id,
                )
            )
            if existente is not None:
                raise OperacaoConflitanteException("Usuario ja vinculado a esta organizacao.")
            vinculo = OrganizacaoUsuario(
                organizacao_id=organizacao_id,
                usuario_id=usuario_id,
                papel=papel,
                ativo=True,
            )
            self.db.add(vinculo)
            self.db.flush()
            self._auditar(admin, "VINCULO_EMPRESA_USUARIO", {
                "organizacao_id": str(organizacao_id),
                "usuario_id": str(usuario_id),
                "papel": papel,
            })
        return vinculo

    def aprovar_conta_dev(self, admin: User, *, usuario_id: UUID) -> Contratacao:
        """Confirma vinculo DEV. Cadastro publico exige verificacao de email."""
        self._admin(admin)
        with self._transacao():
            usuario = self.db.scalar(
                select(User).where(User.id == usuario_id).with_for_update()
            )
            if (usuario is None or usuario.ativo is not True
                    or usuario.perfil != PerfilEnum.CLIENTE):
                raise RecursoNaoEncontradoException("Cliente inexistente ou inativo.")
            if usuario.origem_cadastro != "PUBLICO":
                raise OperacaoConflitanteException(
                    "Cliente legado deve usar a criacao de contrato DEV padrao."
                )
            if usuario.email_verificado_em is None:
                raise OperacaoConflitanteException(
                    "A conta precisa confirmar o e-mail antes de ser aprovada."
                )
            if usuario.situacao_cadastro != "PENDENTE":
                raise OperacaoConflitanteException("Conta ja processada.")
            contrato = self.db.scalar(
                select(Contratacao).where(
                    Contratacao.tipo == "DEV",
                    Contratacao.usuario_cliente_id == usuario_id,
                    Contratacao.situacao.in_(("PENDENTE", "ATIVA")),
                ).with_for_update()
            )
            if contrato is None:
                contrato = Contratacao(
                    tipo="DEV", situacao="ATIVA",
                    usuario_cliente_id=usuario_id,
                )
                self.db.add(contrato)
            else:
                contrato.situacao = "ATIVA"
            usuario.situacao_cadastro = "ATIVO"
            self.db.flush()
            self._auditar(admin, "APROVACAO_CADASTRO_DEV", {
                "usuario_id": str(usuario.id), "contrato_id": str(contrato.id),
            })
        return contrato

    def criar_contrato_dev(self, admin: User, *, usuario_id: UUID) -> Contratacao:
        self._admin(admin)
        with self._transacao():
            self._cliente_apto(usuario_id)
            existente = self.db.scalar(
                select(Contratacao.id).where(
                    Contratacao.tipo == "DEV",
                    Contratacao.usuario_cliente_id == usuario_id,
                    Contratacao.situacao.in_(("PENDENTE", "ATIVA")),
                )
            )
            if existente is not None:
                raise OperacaoConflitanteException("Existe contrato DEV ativo ou pendente.")
            contrato = Contratacao(
                tipo="DEV", situacao="PENDENTE", usuario_cliente_id=usuario_id,
            )
            self.db.add(contrato)
            self.db.flush()
            self._auditar(admin, "CRIACAO_CONTRATO_DEV", {
                "contrato_id": str(contrato.id), "usuario_id": str(usuario_id),
            })
        return contrato

    def criar_contrato_saas(self, admin: User, *, organizacao_id: UUID) -> Contratacao:
        self._admin(admin)
        with self._transacao():
            self._organizacao_ativa(organizacao_id)
            gestor = self.db.scalar(
                select(OrganizacaoUsuario.id).where(
                    OrganizacaoUsuario.organizacao_id == organizacao_id,
                    OrganizacaoUsuario.papel == "GESTOR",
                    OrganizacaoUsuario.ativo.is_(True),
                )
            )
            if gestor is None:
                raise OperacaoConflitanteException(
                    "Uma empresa precisa de um GESTOR ativo antes de contratar SaaS."
                )
            existente = self.db.scalar(
                select(Contratacao.id).where(
                    Contratacao.tipo == "SAAS",
                    Contratacao.organizacao_id == organizacao_id,
                    Contratacao.situacao.in_(("PENDENTE", "ATIVA")),
                )
            )
            if existente is not None:
                raise OperacaoConflitanteException("Contrato SaaS ja existente.")
            contrato = Contratacao(
                tipo="SAAS", situacao="PENDENTE", organizacao_id=organizacao_id,
            )
            self.db.add(contrato)
            self.db.flush()
            self._auditar(admin, "CRIACAO_CONTRATO_SAAS", {
                "contrato_id": str(contrato.id), "organizacao_id": str(organizacao_id),
            })
        return contrato

    def ativar_contrato_dev(self, admin: User, *, contrato_id: UUID) -> Contratacao:
        self._admin(admin)
        with self._transacao():
            contrato = self.db.scalar(
                select(Contratacao).where(Contratacao.id == contrato_id).with_for_update()
            )
            if contrato is None:
                raise RecursoNaoEncontradoException("Contrato nao encontrado.")
            if contrato.tipo != "DEV":
                # Operacoes por empresa ainda nao tem escopo tenant completo.
                raise OperacaoConflitanteException(
                    "Ativacao SaaS bloqueada ate finalizar isolamento empresarial da API."
                )
            if contrato.situacao != "PENDENTE":
                raise OperacaoConflitanteException("Somente contrato pendente pode ser ativado.")
            self._cliente_apto(contrato.usuario_cliente_id)
            contrato.situacao = "ATIVA"
            self._auditar(admin, "ATIVACAO_CONTRATO_DEV", {
                "contrato_id": str(contrato.id),
            })
        return contrato
