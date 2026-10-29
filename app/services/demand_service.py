from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.exceptions import (
    AcessoNegadoException,
    AprovacaoNaoAutorizadaException,
    RecursoNaoEncontradoException,
    RegistroImutavelException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models.aceite_formal import AceiteFormal
from app.domain.models.anexo import Anexo
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum, TipoOcorrenciaEnum
from app.domain.models.etapa_operacional import EtapaOperacional
from app.domain.models.historico_status_pedido import HistoricoStatusPedido
from app.domain.models.ocorrencia import Ocorrencia
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.domain.regras import ciclo_vida
from app.repositories.auditoria_log_repository import AuditoriaLogRepository
from app.repositories.etapa_operacional_repository import EtapaOperacionalRepository
from app.repositories.pedido_repository import PedidoRepository
from app.repositories.user_repository import UserRepository
from app.repositories.ocorrencia_repository import OcorrenciaRepository
from app.repositories.anexo_repository import AnexoRepository
from app.services.aprovacao_service import AprovacaoService
from app.services.demanda_service import DemandAccessDenied, DemandaQueryService
from app.services.pedido_service import PedidoNaoEncontradoError


class DemandService:
    """Regras de negocio do ciclo de vida das demandas sobre o Pedido persistido.

    Toda operacao recebe o usuario autenticado, nunca um ID vindo do corpo da
    requisicao: ele define a permissao e e gravado como autor na auditoria.

    Permissoes:
    - ADMIN: todas as operacoes, exceto aceite/rejeicao (exclusivas do cliente).
    - CLIENTE: cria e edita as proprias demandas, aprova ou rejeita a homologacao
      e envia evidencias.
    - TECNICO responsavel: avanca o estado, gerencia etapas e envia evidencias.
    Demandas fora do escopo de leitura do usuario sao tratadas como inexistentes.
    """

    def __init__(
        self,
        db: Session,
        *,
        anexo_service: Any | None = None,
        aprovacao_service: AprovacaoService | None = None,
    ) -> None:
        self.db = db
        self.pedidos = PedidoRepository(db)
        self.etapas = EtapaOperacionalRepository(db)
        self.auditoria = AuditoriaLogRepository(db)
        self.users = UserRepository(db)
        self.aprovacao = aprovacao_service or AprovacaoService(db)
        # Criado sob demanda: o AnexoService abre o cliente do Supabase Storage.
        self._anexo_service = anexo_service

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def listar(
        self, usuario: User, *, offset: int = 0, limit: int = 100
    ) -> Sequence[Pedido]:
        self._exigir_usuario_ativo(usuario)
        try:
            return DemandaQueryService(self.db).list_demands(
                usuario, offset=offset, limit=limit
            )
        except DemandAccessDenied:
            raise AcessoNegadoException(
                "Perfil sem permissao para consultar demandas."
            ) from None

    def obter(self, usuario: User, pedido_id: UUID) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        try:
            pedido = DemandaQueryService(self.db).get_demand(usuario, pedido_id)
        except DemandAccessDenied:
            raise AcessoNegadoException(
                "Perfil sem permissao para consultar demandas."
            ) from None
        if pedido is None:
            raise RecursoNaoEncontradoException("Demanda nao encontrada.")
        return pedido

    def listar_etapas(
        self, usuario: User, pedido_id: UUID
    ) -> Sequence[EtapaOperacional]:
        pedido = self.obter(usuario, pedido_id)
        return self.etapas.get_by_pedido(pedido.id)

    def listar_auditoria(
        self, usuario: User, pedido_id: UUID
    ) -> Sequence[AuditoriaLog]:
        """Historico somente leitura das acoes sobre a demanda (SCRUM-75)."""
        pedido = self.obter(usuario, pedido_id)
        return self.auditoria.get_by_pedido(pedido.id)

    def listar_estados(self, usuario: User, pedido_id: UUID) -> list[dict[str, Any]]:
        """Linha do tempo dos estados no formato do HistoricoEstadoModel do frontend:
        a criacao (estado_anterior nulo) seguida de cada transicao, com o nome do autor."""
        pedido = self.obter(usuario, pedido_id)
        eventos: list[dict[str, Any]] = []

        criacao = self.db.execute(
            select(AuditoriaLog.created_at, User.nome)
            .join(User, User.id == AuditoriaLog.usuario_id)
            .where(
                AuditoriaLog.pedido_id == pedido.id,
                AuditoriaLog.acao == "CRIACAO_DEMANDA",
            )
            .order_by(AuditoriaLog.created_at)
            .limit(1)
        ).first()
        if criacao is not None:
            eventos.append(
                {
                    "estado_anterior": None,
                    "novo_estado": StatusPedidoEnum.PLANEAMENTO,
                    "usuario_responsavel": criacao.nome,
                    "timestamp": criacao.created_at,
                }
            )

        transicoes = self.db.execute(
            select(HistoricoStatusPedido, User.nome)
            .join(User, User.id == HistoricoStatusPedido.usuario_id)
            .where(HistoricoStatusPedido.pedido_id == pedido.id)
            .order_by(HistoricoStatusPedido.created_at, HistoricoStatusPedido.id)
        )
        for historico, nome in transicoes:
            eventos.append(
                {
                    "estado_anterior": historico.status_anterior,
                    "novo_estado": historico.status_novo,
                    "usuario_responsavel": nome,
                    "timestamp": historico.created_at,
                }
            )
        return eventos

    def listar_ocorrencias(
        self, usuario: User, pedido_id: UUID, *, offset: int, limit: int
    ):
        self.obter(usuario, pedido_id)
        return OcorrenciaRepository(self.db).listar(
            pedido_id, offset=offset, limit=limit
        )

    def obter_ocorrencia(self, usuario: User, pedido_id: UUID, ocorrencia_id: UUID):
        self.obter(usuario, pedido_id)
        registro = OcorrenciaRepository(self.db).obter(pedido_id, ocorrencia_id)
        if registro is None:
            raise RecursoNaoEncontradoException(
                "Ocorrência não encontrada nesta demanda."
            )
        return registro

    def criar_ocorrencia(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        tipo: TipoOcorrenciaEnum,
        descricao: str,
    ):
        descricao = ciclo_vida.validar_texto(descricao, "descrição", 5, 10000)
        if tipo == TipoOcorrenciaEnum.REGRESSO_ESTADO:
            raise RegraNegocioException(
                "Use a rejeição de homologação para registrar um regresso de estado."
            )
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_usuario_ativo(usuario)
            self._bloquear_se_concluido(pedido, "registrar ocorrência")
            registro = OcorrenciaRepository(self.db).create(
                {
                    "pedido_id": pedido_id,
                    "autor_id": usuario.id,
                    "tipo": tipo,
                    "descricao": descricao,
                }
            )
            self._auditar(
                usuario,
                pedido,
                "CRIACAO_OCORRENCIA",
                {"ocorrencia_id": str(registro.id)},
            )
        return registro

    def editar_ocorrencia(
        self, usuario: User, pedido_id: UUID, ocorrencia_id: UUID, *, descricao: str
    ):
        descricao = ciclo_vida.validar_texto(descricao, "descrição", 5, 10000)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_usuario_ativo(usuario)
            self._bloquear_se_concluido(pedido, "editar ocorrência")
            registro = self.obter_ocorrencia(usuario, pedido_id, ocorrencia_id)
            if registro.tipo == TipoOcorrenciaEnum.REGRESSO_ESTADO:
                raise RegistroImutavelException(
                    "O registro de rejeição é somente leitura."
                )
            if not self._is_admin(usuario) and registro.autor_id != usuario.id:
                raise AcessoNegadoException(
                    "Somente o autor ou ADMIN pode editar a ocorrência."
                )
            anterior = registro.descricao
            registro.descricao = descricao
            self._auditar(
                usuario,
                pedido,
                "EDICAO_OCORRENCIA",
                {
                    "ocorrencia_id": str(registro.id),
                    "anterior": anterior,
                    "novo": descricao,
                },
            )
        return registro

    def listar_anexos(self, usuario: User, pedido_id: UUID, *, offset: int, limit: int):
        self.obter(usuario, pedido_id)
        return AnexoRepository(self.db).listar_paginado(
            pedido_id, offset=offset, limit=limit
        )

    def acessar_anexo(self, usuario: User, pedido_id: UUID, anexo_id: UUID):
        self.obter(usuario, pedido_id)
        anexo = AnexoRepository(self.db).get_by_id(anexo_id)
        if anexo is None or anexo.pedido_id != pedido_id:
            raise RecursoNaoEncontradoException("Anexo não encontrado nesta demanda.")
        return self.anexo_service.storage.signed_url(
            anexo.caminho_storage, expires_in=60
        )

    # ------------------------------------------------------------------
    # Cadastro e edicao (SCRUM-20)
    # ------------------------------------------------------------------

    def criar(
        self,
        usuario: User,
        *,
        titulo: str,
        descricao: str,
        cliente_id: UUID | None = None,
    ) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        self._exigir_perfil(usuario, PerfilEnum.ADMIN, PerfilEnum.CLIENTE)

        if usuario.perfil == PerfilEnum.CLIENTE:
            if cliente_id is not None and cliente_id != usuario.id:
                raise AcessoNegadoException(
                    "O cliente so pode cadastrar demandas para si mesmo."
                )
            cliente_id = usuario.id
        elif cliente_id is None:
            raise AcessoNegadoException("Informe o cliente da demanda.")

        titulo = ciclo_vida.validar_texto(titulo, "titulo", 3, 255)
        descricao = ciclo_vida.validar_texto(descricao, "descricao", 5)

        with self._transacao():
            self._obter_usuario_com_perfil(cliente_id, PerfilEnum.CLIENTE, "cliente")
            pedido = self.pedidos.create(
                {
                    "codigo_identificador": f"DEM-{uuid4().hex[:8].upper()}",
                    "titulo": titulo,
                    "descricao": descricao,
                    "status": StatusPedidoEnum.PLANEAMENTO,
                    "percentual_progresso": ciclo_vida.calcular_progresso(
                        StatusPedidoEnum.PLANEAMENTO
                    ),
                    "cliente_id": cliente_id,
                }
            )
            self._auditar(
                usuario,
                pedido,
                "CRIACAO_DEMANDA",
                {
                    "codigo_identificador": pedido.codigo_identificador,
                    "titulo": titulo,
                },
            )
        return pedido

    def editar(
        self, usuario: User, pedido_id: UUID, *, titulo: str, descricao: str
    ) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        titulo = ciclo_vida.validar_texto(titulo, "titulo", 3, 255)
        descricao = ciclo_vida.validar_texto(descricao, "descricao", 5)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            if not self._is_admin(usuario) and not self._is_cliente_dono(
                usuario, pedido
            ):
                raise AcessoNegadoException(
                    "Somente o cliente da demanda ou um ADMIN pode edita-la."
                )
            self._bloquear_se_concluido(pedido, "editar a demanda")

            anterior = {"titulo": pedido.titulo, "descricao": pedido.descricao}
            pedido.titulo = titulo
            pedido.descricao = descricao
            self._auditar(
                usuario,
                pedido,
                "EDICAO_DEMANDA",
                {
                    "anterior": anterior,
                    "novo": {"titulo": titulo, "descricao": descricao},
                },
            )
        return pedido

    def excluir(self, usuario: User, pedido_id: UUID) -> None:
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_perfil(usuario, PerfilEnum.ADMIN)
            self._bloquear_se_concluido(pedido, "excluir a demanda")
            # O log sobrevive a exclusao: auditoria_logs.pedido_id e ON DELETE SET NULL.
            self._auditar(
                usuario,
                pedido,
                "EXCLUSAO_DEMANDA",
                {
                    "pedido_id": str(pedido.id),
                    "codigo_identificador": pedido.codigo_identificador,
                },
            )
            self.pedidos.delete(pedido)

    # ------------------------------------------------------------------
    # Maquina de estados
    # ------------------------------------------------------------------

    def alterar_status(
        self, usuario: User, pedido_id: UUID, novo_status: StatusPedidoEnum
    ) -> Pedido:
        """Avanca PLANEAMENTO -> EXECUCAO -> HOMOLOGACAO. A saida de HOMOLOGACAO
        e exclusiva do cliente: aprovar_homologacao ou rejeitar_homologacao."""
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_equipe_operacional(usuario, pedido)

            status_atual = pedido.status
            if (
                status_atual == StatusPedidoEnum.HOMOLOGACAO
                and novo_status == StatusPedidoEnum.EXECUCAO
            ):
                raise TransicaoEstadoInvalidaException(
                    "O retorno de HOMOLOGACAO para EXECUCAO e feito pela rejeicao do cliente."
                )

            etapas = self.etapas.get_by_pedido(pedido.id)
            ciclo_vida.validar_transicao(
                status_atual,
                novo_status,
                total_etapas=len(etapas),
                etapas_pendentes=tuple(
                    etapa.descricao for etapa in etapas if not etapa.concluida
                ),
            )

            pedido.status = novo_status
            self._recalcular_progresso(pedido, etapas)
            self._registrar_historico(usuario, pedido, status_atual, novo_status)
            self._auditar(
                usuario,
                pedido,
                "ALTERACAO_ESTADO",
                {
                    "status_anterior": status_atual.value,
                    "status_novo": novo_status.value,
                },
            )
        return pedido

    def aprovar_homologacao(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        versao_entregavel: str,
        declaracao_aceite: str,
    ) -> AceiteFormal:
        """Aceite formal (SCRUM-72): somente o cliente dono da demanda, identificado
        pelo usuario autenticado, conclui a demanda."""
        pedido = self.obter(usuario, pedido_id)
        if not self._is_cliente_dono(usuario, pedido):
            raise AprovacaoNaoAutorizadaException(
                "Somente o cliente da demanda pode registrar o aceite formal."
            )
        if pedido.status == StatusPedidoEnum.CONCLUIDO:
            raise RegistroImutavelException(
                "A demanda ja possui aceite formal e esta concluida."
            )
        if pedido.status != StatusPedidoEnum.HOMOLOGACAO:
            raise TransicaoEstadoInvalidaException(
                f"Apenas demandas em HOMOLOGACAO podem ser aprovadas. Estado atual: {pedido.status.value}."
            )
        versao_entregavel = ciclo_vida.validar_texto(
            versao_entregavel, "versao do entregavel", 1, 50
        )
        declaracao_aceite = ciclo_vida.validar_texto(
            declaracao_aceite, "declaracao de aceite", 10
        )

        try:
            # O AprovacaoService bloqueia o pedido, revalida o cliente e grava
            # aceite, historico e auditoria numa unica transacao.
            return self.aprovacao.registrar_aceite(
                pedido_id=pedido.id,
                cliente_id=usuario.id,
                versao_entregavel=versao_entregavel,
                declaracao_aceite=declaracao_aceite,
                status_esperado=StatusPedidoEnum.HOMOLOGACAO,
            )
        except PermissionError as erro:
            raise AprovacaoNaoAutorizadaException(str(erro)) from None
        except PedidoNaoEncontradoError:
            raise RecursoNaoEncontradoException("Demanda nao encontrada.") from None
        except IntegrityError:
            raise RegistroImutavelException(
                "A demanda ja possui aceite formal registrado."
            ) from None
        except ValueError as erro:
            # Entradas ja foram validadas: resta a mudanca de estado concorrente.
            raise TransicaoEstadoInvalidaException(str(erro)) from None

    def rejeitar_homologacao(
        self, usuario: User, pedido_id: UUID, *, motivo: str
    ) -> Pedido:
        """Devolve a demanda para EXECUCAO e registra a ocorrencia de regresso."""
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            if not self._is_cliente_dono(usuario, pedido):
                raise AprovacaoNaoAutorizadaException(
                    "Somente o cliente da demanda pode rejeitar a homologacao."
                )
            if pedido.status != StatusPedidoEnum.HOMOLOGACAO:
                raise TransicaoEstadoInvalidaException(
                    f"Apenas demandas em HOMOLOGACAO podem ser rejeitadas. Estado atual: {pedido.status.value}."
                )

            status_atual = pedido.status
            motivo = ciclo_vida.validar_motivo_regresso(motivo)
            ciclo_vida.validar_transicao(
                status_atual, StatusPedidoEnum.EXECUCAO, motivo_regresso=motivo
            )

            pedido.status = StatusPedidoEnum.EXECUCAO
            self._recalcular_progresso(pedido)
            ocorrencia = Ocorrencia(
                pedido_id=pedido.id,
                autor_id=usuario.id,
                tipo=TipoOcorrenciaEnum.REGRESSO_ESTADO,
                descricao=motivo,
                motivo_regresso=motivo,
                status_anterior=status_atual,
                status_novo=StatusPedidoEnum.EXECUCAO,
            )
            self.db.add(ocorrencia)
            self.db.flush()
            self._registrar_historico(
                usuario, pedido, status_atual, StatusPedidoEnum.EXECUCAO
            )
            self._auditar(
                usuario,
                pedido,
                "REJEICAO_HOMOLOGACAO",
                {
                    "ocorrencia_id": str(ocorrencia.id),
                    "motivo": motivo,
                },
            )
        return pedido

    # ------------------------------------------------------------------
    # Etapas operacionais (SCRUM-71)
    # ------------------------------------------------------------------

    def adicionar_etapa(
        self, usuario: User, pedido_id: UUID, *, descricao: str
    ) -> EtapaOperacional:
        self._exigir_usuario_ativo(usuario)
        descricao = ciclo_vida.validar_texto(descricao, "descricao da etapa", 3, 255)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_equipe_operacional(usuario, pedido)
            if pedido.status not in (
                StatusPedidoEnum.PLANEAMENTO,
                StatusPedidoEnum.EXECUCAO,
            ):
                raise TransicaoEstadoInvalidaException(
                    "Etapas so podem ser adicionadas em PLANEAMENTO ou EXECUCAO. "
                    f"Estado atual: {pedido.status.value}."
                )

            etapa = self.etapas.create(
                {
                    "pedido_id": pedido.id,
                    "descricao": descricao,
                    "criado_por_id": usuario.id,
                }
            )
            self._recalcular_progresso(pedido)
            self._auditar(
                usuario,
                pedido,
                "CADASTRO_ETAPA",
                {
                    "etapa_id": str(etapa.id),
                    "descricao": descricao,
                },
            )
        return etapa

    def concluir_etapa(
        self, usuario: User, pedido_id: UUID, etapa_id: UUID
    ) -> EtapaOperacional:
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_equipe_operacional(usuario, pedido)
            if pedido.status != StatusPedidoEnum.EXECUCAO:
                raise TransicaoEstadoInvalidaException(
                    f"Etapas so podem ser concluidas em EXECUCAO. Estado atual: {pedido.status.value}."
                )

            etapa = self.etapas.get_by_id_and_pedido(etapa_id, pedido.id)
            if etapa is None:
                raise RecursoNaoEncontradoException(
                    "Etapa nao encontrada nesta demanda."
                )
            if etapa.concluida:
                raise TransicaoEstadoInvalidaException("A etapa ja esta concluida.")

            etapa.concluida = True
            etapa.concluida_em = self._agora()
            etapa.concluida_por_id = usuario.id
            self.db.flush()
            self._recalcular_progresso(pedido)
            self._auditar(
                usuario,
                pedido,
                "CONCLUSAO_ETAPA",
                {
                    "etapa_id": str(etapa.id),
                    "descricao": etapa.descricao,
                },
            )
        return etapa

    # ------------------------------------------------------------------
    # Atribuicao e evidencias (SCRUM-75)
    # ------------------------------------------------------------------

    def atribuir_responsavel(
        self, usuario: User, pedido_id: UUID, *, responsavel_id: UUID
    ) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        self._exigir_perfil(usuario, PerfilEnum.ADMIN)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._bloquear_se_concluido(pedido, "alterar o responsavel")
            self._obter_usuario_com_perfil(
                responsavel_id, PerfilEnum.TECNICO, "responsavel"
            )

            anterior = pedido.responsavel_id
            pedido.responsavel_id = responsavel_id
            self._auditar(
                usuario,
                pedido,
                "ATRIBUICAO_RESPONSAVEL",
                {
                    "responsavel_anterior": str(anterior) if anterior else None,
                    "responsavel_novo": str(responsavel_id),
                },
            )
        return pedido

    def registrar_evidencia(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        nome_arquivo: str,
        conteudo: bytes,
        ocorrencia_id: UUID | None = None,
    ) -> Anexo:
        """Valida o conteudo real do arquivo, envia ao Storage e audita o envio.

        O pedido fica bloqueado (FOR UPDATE) ate o commit do AnexoService, para
        que nao seja concluido entre a verificacao e a gravacao do anexo."""
        self._exigir_usuario_ativo(usuario)
        try:
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._bloquear_se_concluido(pedido, "enviar evidencias")
            if ocorrencia_id is not None:
                ocorrencia = self.db.get(Ocorrencia, ocorrencia_id)
                if ocorrencia is None or ocorrencia.pedido_id != pedido.id:
                    raise RecursoNaoEncontradoException(
                        "Ocorrencia nao encontrada nesta demanda."
                    )
        except Exception:
            self.db.rollback()
            raise

        try:
            return self.anexo_service.criar(
                pedido_id=pedido.id,
                enviado_por_id=usuario.id,
                nome_arquivo=nome_arquivo,
                conteudo=conteudo,
                ocorrencia_id=ocorrencia_id,
            )
        except Exception:
            # Arquivo invalido ou falha no Storage acontecem antes do rollback do
            # AnexoService; libera o bloqueio do pedido.
            self.db.rollback()
            raise

    @property
    def anexo_service(self):
        if self._anexo_service is None:
            from app.services.anexo_service import AnexoService

            self._anexo_service = AnexoService(self.db)
        return self._anexo_service

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

    @staticmethod
    def _agora() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _exigir_usuario_ativo(usuario: User | None) -> None:
        if usuario is None or usuario.id is None or usuario.ativo is not True:
            raise AcessoNegadoException(
                "A operacao exige um usuario autenticado e ativo."
            )

    @staticmethod
    def _exigir_perfil(usuario: User, *perfis: PerfilEnum) -> None:
        if usuario.perfil not in perfis:
            raise AcessoNegadoException("Perfil sem permissao para esta operacao.")

    @staticmethod
    def _is_admin(usuario: User) -> bool:
        return usuario.perfil == PerfilEnum.ADMIN

    @staticmethod
    def _is_cliente_dono(usuario: User, pedido: Pedido) -> bool:
        return usuario.perfil == PerfilEnum.CLIENTE and pedido.cliente_id == usuario.id

    @staticmethod
    def _is_responsavel(usuario: User, pedido: Pedido) -> bool:
        return (
            usuario.perfil == PerfilEnum.TECNICO and pedido.responsavel_id == usuario.id
        )

    def _exigir_equipe_operacional(self, usuario: User, pedido: Pedido) -> None:
        if not self._is_admin(usuario) and not self._is_responsavel(usuario, pedido):
            raise AcessoNegadoException(
                "Somente o tecnico responsavel ou um ADMIN pode executar esta operacao."
            )

    def _bloquear_pedido_visivel(self, usuario: User, pedido_id: UUID) -> Pedido:
        """Carrega o pedido com bloqueio de linha e aplica o escopo de leitura."""
        pedido = self.db.scalar(
            select(Pedido)
            .where(Pedido.id == pedido_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        visivel = pedido is not None and (
            self._is_admin(usuario)
            or self._is_cliente_dono(usuario, pedido)
            or self._is_responsavel(usuario, pedido)
        )
        if not visivel:
            raise RecursoNaoEncontradoException("Demanda nao encontrada.")
        return pedido

    @staticmethod
    def _bloquear_se_concluido(pedido: Pedido, operacao: str) -> None:
        if pedido.status == StatusPedidoEnum.CONCLUIDO:
            raise RegistroImutavelException(
                f"Demandas CONCLUIDAS sao imutaveis: nao e permitido {operacao}."
            )

    def _obter_usuario_com_perfil(
        self, usuario_id: UUID, perfil: PerfilEnum, papel: str
    ) -> User:
        alvo = self.users.get_by_id(usuario_id)
        if alvo is None or alvo.ativo is not True or alvo.perfil != perfil:
            raise RecursoNaoEncontradoException(
                f"O {papel} informado nao existe ou nao e um {perfil.value} ativo."
            )
        return alvo

    def _recalcular_progresso(
        self, pedido: Pedido, etapas: Sequence[EtapaOperacional] | None = None
    ) -> None:
        if etapas is None:
            self.db.flush()
            etapas = self.etapas.get_by_pedido(pedido.id)
        concluidas = sum(1 for etapa in etapas if etapa.concluida)
        pedido.percentual_progresso = ciclo_vida.calcular_progresso(
            pedido.status, len(etapas), concluidas
        )

    def _registrar_historico(
        self,
        usuario: User,
        pedido: Pedido,
        status_anterior: StatusPedidoEnum,
        status_novo: StatusPedidoEnum,
    ) -> None:
        self.db.add(
            HistoricoStatusPedido(
                pedido_id=pedido.id,
                usuario_id=usuario.id,
                status_anterior=status_anterior,
                status_novo=status_novo,
                created_at=self._agora(),
            )
        )

    def _auditar(
        self, usuario: User, pedido: Pedido, acao: str, detalhes: dict[str, Any]
    ) -> None:
        self.db.add(
            AuditoriaLog(
                usuario_id=usuario.id,
                pedido_id=pedido.id,
                acao=acao,
                detalhes=detalhes,
                created_at=self._agora(),
            )
        )
        self.db.flush()
