from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID, uuid4

from sqlalchemy import func, select # type: ignore
from sqlalchemy.exc import IntegrityError # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.core.exceptions import (
    AcessoNegadoException,
    AprovacaoNaoAutorizadaException,
    OperacaoConflitanteException,
    RecursoNaoEncontradoException,
    RegistroImutavelException,
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
from app.domain.regras import autorizacao, ciclo_vida
from app.repositories.auditoria_log_repository import AuditoriaLogRepository
from app.repositories.anexo_repository import AnexoRepository
from app.repositories.etapa_operacional_repository import EtapaOperacionalRepository
from app.repositories.pedido_repository import PedidoRepository
from app.repositories.user_repository import UserRepository
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
        storage_settings=None,
    ) -> None:
        self.db = db
        self.pedidos = PedidoRepository(db)
        self.etapas = EtapaOperacionalRepository(db)
        self.auditoria = AuditoriaLogRepository(db)
        self.users = UserRepository(db)
        self.aprovacao = aprovacao_service or AprovacaoService(db)
        # Criado sob demanda: o AnexoService abre o cliente do Supabase Storage.
        self._anexo_service = anexo_service
        self._storage_settings = storage_settings

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def listar(self, usuario: User, *, offset: int = 0, limit: int = 100) -> Sequence[Pedido]:
        self._exigir_usuario_ativo(usuario)
        try:
            return DemandaQueryService(self.db).list_demands(usuario, offset=offset, limit=limit)
        except DemandAccessDenied:
            raise AcessoNegadoException("Perfil sem permissao para consultar demandas.") from None

    def obter(self, usuario: User, pedido_id: UUID) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        try:
            pedido = DemandaQueryService(self.db).get_demand(usuario, pedido_id)
        except DemandAccessDenied:
            raise AcessoNegadoException("Perfil sem permissao para consultar demandas.") from None
        if pedido is None:
            raise RecursoNaoEncontradoException("Demanda nao encontrada.")
        return pedido

    def listar_etapas(self, usuario: User, pedido_id: UUID) -> Sequence[EtapaOperacional]:
        pedido = self.obter(usuario, pedido_id)
        return self.etapas.get_by_pedido(pedido.id)

    def listar_anexos(self, usuario: User, pedido_id: UUID, *, offset=0, limit=100):
        pedido = self.obter(usuario, pedido_id)
        return AnexoRepository(self.db).listar_pagina(pedido.id, offset=offset, limit=limit)

    def acessar_anexo(self, usuario: User, pedido_id: UUID, anexo_id: UUID):
        pedido = self.obter(usuario, pedido_id)
        anexo = AnexoRepository(self.db).get_by_id(anexo_id)
        if anexo is None or anexo.pedido_id != pedido.id:
            raise RecursoNaoEncontradoException("Anexo nao encontrado nesta demanda.")
        if not anexo.caminho_storage.startswith(f"pedidos/{pedido.id}/"):
            from app.infrastructure.storage.supabase_storage import StorageReadError
            raise StorageReadError("Referencia de arquivo indisponivel.")
        return self.anexo_service.storage.create_signed_url(anexo.caminho_storage, expires_in=300)

    def listar_auditoria(self, usuario: User, pedido_id: UUID) -> Sequence[AuditoriaLog]:
        """Historico somente leitura das acoes sobre a demanda (SCRUM-75)."""
        pedido = self.obter(usuario, pedido_id)
        return self.auditoria.get_by_pedido(pedido.id)

    def listar_estados(self, usuario: User, pedido_id: UUID) -> list[dict[str, Any]]:
        """Linha do tempo dos estados no formato do HistoricoEstadoModel do frontend:
        a criacao (estado_anterior nulo) seguida de cada transicao, com o nome do
        autor, conforme o PR #12 da HML."""
        pedido = self.obter(usuario, pedido_id)
        eventos: list[dict[str, Any]] = []

        criacao = self.db.execute(
            select(AuditoriaLog.created_at, User.nome)
            .join(User, User.id == AuditoriaLog.usuario_id)
            .where(AuditoriaLog.pedido_id == pedido.id, AuditoriaLog.acao == "CRIACAO_DEMANDA")
            .order_by(AuditoriaLog.created_at)
            .limit(1)
        ).first()
        if criacao is not None:
            eventos.append({
                "estado_anterior": None,
                "novo_estado": StatusPedidoEnum.PLANEAMENTO,
                "usuario_responsavel": criacao.nome,
                "timestamp": criacao.created_at,
            })

        transicoes = self.db.execute(
            select(HistoricoStatusPedido, User.nome)
            .join(User, User.id == HistoricoStatusPedido.usuario_id)
            .where(HistoricoStatusPedido.pedido_id == pedido.id)
            .order_by(HistoricoStatusPedido.created_at, HistoricoStatusPedido.id)
        )
        for historico, nome in transicoes:
            eventos.append({
                "estado_anterior": historico.status_anterior,
                "novo_estado": historico.status_novo,
                "usuario_responsavel": nome,
                "timestamp": historico.created_at,
            })
        return eventos

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
                raise AcessoNegadoException("O cliente so pode cadastrar demandas para si mesmo.")
            cliente_id = usuario.id
        elif cliente_id is None:
            raise AcessoNegadoException("Informe o cliente da demanda.")

        titulo = ciclo_vida.validar_texto(titulo, "titulo", 3, 255)
        descricao = ciclo_vida.validar_texto(descricao, "descricao", 5)

        with self._transacao():
            self._obter_usuario_com_perfil(cliente_id, PerfilEnum.CLIENTE, "cliente")
            pedido = self.pedidos.create({
                "codigo_identificador": f"DEM-{uuid4().hex[:8].upper()}",
                "titulo": titulo,
                "descricao": descricao,
                "status": StatusPedidoEnum.PLANEAMENTO,
                "percentual_progresso": ciclo_vida.calcular_progresso(StatusPedidoEnum.PLANEAMENTO),
                "cliente_id": cliente_id,
            })
            self._auditar(usuario, pedido, "CRIACAO_DEMANDA", {
                "codigo_identificador": pedido.codigo_identificador,
                "titulo": titulo,
            })
        return pedido

    def editar(self, usuario: User, pedido_id: UUID, *, titulo: str, descricao: str) -> Pedido:
        self._exigir_usuario_ativo(usuario)
        titulo = ciclo_vida.validar_texto(titulo, "titulo", 3, 255)
        descricao = ciclo_vida.validar_texto(descricao, "descricao", 5)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            autorizacao.exigir_dono_ou_admin(usuario, pedido, "edita-la")
            self._bloquear_se_concluido(pedido, "editar a demanda")

            anterior = {"titulo": pedido.titulo, "descricao": pedido.descricao}
            pedido.titulo = titulo
            pedido.descricao = descricao
            self._auditar(usuario, pedido, "EDICAO_DEMANDA", {
                "anterior": anterior,
                "novo": {"titulo": titulo, "descricao": descricao},
            })
        return pedido

    def excluir(self, usuario: User, pedido_id: UUID) -> None:
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_perfil(usuario, PerfilEnum.ADMIN)
            self._bloquear_se_concluido(pedido, "excluir a demanda")
            # O log sobrevive a exclusao: auditoria_logs.pedido_id e ON DELETE SET NULL.
            self._auditar(usuario, pedido, "EXCLUSAO_DEMANDA", {
                "pedido_id": str(pedido.id),
                "codigo_identificador": pedido.codigo_identificador,
            })
            self.pedidos.delete(pedido)

    # ------------------------------------------------------------------
    # Maquina de estados
    # ------------------------------------------------------------------

    def alterar_status(self, usuario: User, pedido_id: UUID, novo_status: StatusPedidoEnum) -> Pedido:
        """Avanca PLANEAMENTO -> EXECUCAO -> HOMOLOGACAO. A saida de HOMOLOGACAO
        e exclusiva do cliente: aprovar_homologacao ou rejeitar_homologacao."""
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            status_atual = pedido.status
            etapas = self.etapas.get_by_pedido(pedido.id)
            self.validar_alteracao_status(usuario, pedido, novo_status, etapas)

            pedido.status = novo_status
            self._recalcular_progresso(pedido, etapas)
            self._registrar_historico(usuario, pedido, status_atual, novo_status)
            self._auditar(usuario, pedido, "ALTERACAO_ESTADO", {
                "status_anterior": status_atual.value,
                "status_novo": novo_status.value,
            })
        return pedido

    def validar_alteracao_status(self, usuario, pedido, novo_status, etapas):
        """Shared by the REST use case and the legacy compatibility service."""
        self._exigir_usuario_ativo(usuario)
        self._exigir_equipe_operacional(usuario, pedido)
        if pedido.status == StatusPedidoEnum.HOMOLOGACAO and novo_status == StatusPedidoEnum.EXECUCAO:
            raise TransicaoEstadoInvalidaException(
                "O retorno de HOMOLOGACAO para EXECUCAO e feito pela rejeicao do cliente."
            )
        ciclo_vida.validar_transicao(
            pedido.status, novo_status,
            total_etapas=len(etapas),
            etapas_pendentes=tuple(e.descricao for e in etapas if not e.concluida),
            ocorrencias_abertas=self._contar_ocorrencias_abertas(pedido.id),
        )

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
            raise AprovacaoNaoAutorizadaException("Somente o cliente da demanda pode registrar o aceite formal.")
        if pedido.status == StatusPedidoEnum.CONCLUIDO:
            raise RegistroImutavelException("A demanda ja possui aceite formal e esta concluida.")
        if pedido.status != StatusPedidoEnum.HOMOLOGACAO:
            raise TransicaoEstadoInvalidaException(
                f"Apenas demandas em HOMOLOGACAO podem ser aprovadas. Estado atual: {pedido.status.value}."
            )
        versao_entregavel = ciclo_vida.validar_texto(versao_entregavel, "versao do entregavel", 1, 50)
        declaracao_aceite = ciclo_vida.validar_texto(declaracao_aceite, "declaracao de aceite", 10)

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
            raise RegistroImutavelException("A demanda ja possui aceite formal registrado.") from None
        except ValueError as erro:
            # Entradas ja foram validadas: resta a mudanca de estado concorrente.
            raise TransicaoEstadoInvalidaException(str(erro)) from None

    def rejeitar_homologacao(self, usuario: User, pedido_id: UUID, *, motivo: str) -> Pedido:
        """Devolve a demanda para EXECUCAO e registra a ocorrencia de regresso."""
        self._exigir_usuario_ativo(usuario)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            if not self._is_cliente_dono(usuario, pedido):
                raise AprovacaoNaoAutorizadaException("Somente o cliente da demanda pode rejeitar a homologacao.")
            if pedido.status != StatusPedidoEnum.HOMOLOGACAO:
                raise TransicaoEstadoInvalidaException(
                    f"Apenas demandas em HOMOLOGACAO podem ser rejeitadas. Estado atual: {pedido.status.value}."
                )

            status_atual = pedido.status
            motivo = ciclo_vida.validar_motivo_regresso(motivo)
            ciclo_vida.validar_transicao(status_atual, StatusPedidoEnum.EXECUCAO, motivo_regresso=motivo)

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
            self._registrar_historico(usuario, pedido, status_atual, StatusPedidoEnum.EXECUCAO)
            self._auditar(usuario, pedido, "REJEICAO_HOMOLOGACAO", {
                "ocorrencia_id": str(ocorrencia.id),
                "motivo": motivo,
            })
        return pedido

    # ------------------------------------------------------------------
    # Etapas operacionais (SCRUM-71)
    # ------------------------------------------------------------------

    def adicionar_etapa(self, usuario: User, pedido_id: UUID, *, descricao: str, ordem: int | None = None) -> EtapaOperacional:
        self._exigir_usuario_ativo(usuario)
        descricao = ciclo_vida.validar_texto(descricao, "descricao da etapa", 3, 255)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_equipe_operacional(usuario, pedido)
            if pedido.status not in (StatusPedidoEnum.PLANEAMENTO, StatusPedidoEnum.EXECUCAO):
                raise TransicaoEstadoInvalidaException(
                    "Etapas so podem ser adicionadas em PLANEAMENTO ou EXECUCAO. "
                    f"Estado atual: {pedido.status.value}."
                )

            etapas = list(self.etapas.get_by_pedido(pedido.id))
            posicao = len(etapas) + 1 if ordem is None else ordem
            self._validar_posicao_etapa(posicao, len(etapas) + 1)
            etapa = self.etapas.create({
                "pedido_id": pedido.id,
                "descricao": descricao,
                "criado_por_id": usuario.id,
                "ordem": posicao,
            })
            etapas.insert(posicao - 1, etapa)
            self._ordenar_etapas(etapas)
            self._recalcular_progresso(pedido)
            self._auditar(usuario, pedido, "CADASTRO_ETAPA", {
                "etapa_id": str(etapa.id),
                "descricao": descricao,
                "ordem": posicao,
            })
        return etapa

    @staticmethod
    def _validar_posicao_etapa(ordem: int, total: int) -> None:
        if type(ordem) is not int or not 1 <= ordem <= total:
            raise OperacaoConflitanteException(f"A ordem deve estar entre 1 e {total}.")

    def _ordenar_etapas(self, etapas) -> None:
        for posicao, etapa in enumerate(etapas, 1):
            etapa.ordem = posicao
        self.db.flush()

    def _etapa_mutavel(self, usuario, pedido, etapa_id):
        self._exigir_equipe_operacional(usuario, pedido)
        if pedido.status not in (StatusPedidoEnum.PLANEAMENTO, StatusPedidoEnum.EXECUCAO):
            raise TransicaoEstadoInvalidaException("Etapas so podem ser alteradas em PLANEAMENTO ou EXECUCAO.")
        etapa = self.etapas.get_by_id_and_pedido(etapa_id, pedido.id)
        if etapa is None:
            raise RecursoNaoEncontradoException("Etapa nao encontrada nesta demanda.")
        if etapa.concluida:
            raise RegistroImutavelException("Etapas concluidas nao podem ser editadas ou removidas.")
        return etapa

    def editar_etapa(self, usuario, pedido_id, etapa_id, *, descricao=None, ordem=None):
        self._exigir_usuario_ativo(usuario)
        if descricao is not None:
            descricao = ciclo_vida.validar_texto(descricao, "descricao da etapa", 3, 255)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            etapa = self._etapa_mutavel(usuario, pedido, etapa_id)
            anterior = {"descricao": etapa.descricao, "ordem": etapa.ordem}
            etapas = list(self.etapas.get_by_pedido(pedido.id))
            if ordem is not None:
                self._validar_posicao_etapa(ordem, len(etapas))
                etapas.remove(etapa)
                etapas.insert(ordem - 1, etapa)
                self._ordenar_etapas(etapas)
            if descricao is not None:
                etapa.descricao = descricao
            self._recalcular_progresso(pedido)
            self._auditar(usuario, pedido, "EDICAO_ETAPA", {
                "etapa_id": str(etapa.id), "anterior": anterior,
                "novo": {"descricao": etapa.descricao, "ordem": etapa.ordem},
            })
        return etapa

    def remover_etapa(self, usuario, pedido_id, etapa_id, *, motivo):
        self._exigir_usuario_ativo(usuario)
        motivo = ciclo_vida.validar_texto(motivo, "motivo", 10, 500)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            etapa = self._etapa_mutavel(usuario, pedido, etapa_id)
            detalhes = {"etapa_id": str(etapa.id), "descricao": etapa.descricao,
                        "ordem": etapa.ordem, "motivo": motivo}
            self.etapas.delete(etapa)
            self._ordenar_etapas(self.etapas.get_by_pedido(pedido.id))
            self._recalcular_progresso(pedido)
            self._auditar(usuario, pedido, "REMOCAO_ETAPA", detalhes)

    def concluir_etapa(self, usuario: User, pedido_id: UUID, etapa_id: UUID) -> EtapaOperacional:
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
                raise RecursoNaoEncontradoException("Etapa nao encontrada nesta demanda.")
            if etapa.concluida:
                raise TransicaoEstadoInvalidaException("A etapa ja esta concluida.")

            etapa.concluida = True
            etapa.concluida_em = self._agora()
            etapa.concluida_por_id = usuario.id
            self.db.flush()
            self._recalcular_progresso(pedido)
            self._auditar(usuario, pedido, "CONCLUSAO_ETAPA", {
                "etapa_id": str(etapa.id),
                "descricao": etapa.descricao,
            })
        return etapa

    # ------------------------------------------------------------------
    # Atribuicao e evidencias (SCRUM-75)
    # ------------------------------------------------------------------

    def listar_fila_atendimento(self, usuario: User, *, offset: int, limit: int) -> Sequence[Pedido]:
        self._exigir_perfil(usuario, PerfilEnum.TECNICO)
        return self.db.scalars(
            select(Pedido)
            .where(
                Pedido.responsavel_id.is_(None),
                Pedido.status == StatusPedidoEnum.PLANEAMENTO,
            )
            .order_by(Pedido.created_at, Pedido.id)
            .offset(offset)
            .limit(limit)
        ).all()

    def assumir_demanda(self, usuario: User, pedido_id: UUID) -> None:
        self._exigir_perfil(usuario, PerfilEnum.TECNICO)
        with self._transacao():
            pedido = self.pedidos.get_by_id_for_update(pedido_id)
            if pedido is None:
                raise RecursoNaoEncontradoException("Demanda nao encontrada.")
            if pedido.responsavel_id == usuario.id:
                return
            if pedido.responsavel_id is not None or pedido.status != StatusPedidoEnum.PLANEAMENTO:
                raise OperacaoConflitanteException("A demanda nao esta mais disponivel na fila.")
            self._registrar_responsavel(usuario, pedido, usuario.id, None)

    def atribuir_responsavel(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        responsavel_id: UUID,
        motivo: str | None = None,
    ) -> Pedido:
        """Atribui ou reatribui o tecnico responsavel (SCRUM-97).

        A primeira atribuicao dispensa justificativa; trocar um tecnico ja
        atribuido exige motivo, porque tira a demanda de quem a executava e o
        historico precisa explicar a troca."""
        self._exigir_usuario_ativo(usuario)
        self._exigir_perfil(usuario, PerfilEnum.ADMIN)
        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._bloquear_se_concluido(pedido, "alterar o responsavel")
            self._obter_usuario_com_perfil(responsavel_id, PerfilEnum.TECNICO, "responsavel")

            anterior = pedido.responsavel_id
            if anterior == responsavel_id:
                raise OperacaoConflitanteException("Este tecnico ja e o responsavel pela demanda.")
            if anterior is not None:
                motivo = ciclo_vida.validar_texto(motivo, "motivo da reatribuicao", 10, 500)
            elif motivo is not None:
                motivo = motivo.strip() or None

            self._registrar_responsavel(usuario, pedido, responsavel_id, motivo)
        return pedido

    def _registrar_responsavel(
        self, usuario: User, pedido: Pedido, responsavel_id: UUID, motivo: str | None
    ) -> None:
        anterior = pedido.responsavel_id
        pedido.responsavel_id = responsavel_id
        self._auditar(usuario, pedido, "ATRIBUICAO_RESPONSAVEL", {
            "responsavel_anterior": str(anterior) if anterior else None,
            "responsavel_novo": str(responsavel_id),
            "motivo": motivo,
        })

    # ------------------------------------------------------------------
    # Ocorrencias e correcoes (SCRUM-98)
    # ------------------------------------------------------------------

    def listar_ocorrencias(self, usuario: User, pedido_id: UUID) -> Sequence[Ocorrencia]:
        pedido = self.obter(usuario, pedido_id)
        return self.db.scalars(
            select(Ocorrencia)
            .where(Ocorrencia.pedido_id == pedido.id)
            .order_by(Ocorrencia.created_at, Ocorrencia.id)
        ).all()

    def registrar_ocorrencia(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        tipo: TipoOcorrenciaEnum,
        descricao: str,
    ) -> Ocorrencia:
        """Abre um erro ou pedido de correcao. Qualquer pessoa vinculada a demanda
        (cliente dono, tecnico responsavel ou ADMIN) pode registrar; enquanto
        houver ocorrencia aberta a demanda nao vai para HOMOLOGACAO."""
        self._exigir_usuario_ativo(usuario)
        ciclo_vida.validar_tipo_ocorrencia_manual(tipo)
        descricao = ciclo_vida.validar_texto(descricao, "descricao da ocorrencia", 10, 2000)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            ciclo_vida.validar_estado_para_ocorrencia(pedido.status)
            ocorrencia = Ocorrencia(
                pedido_id=pedido.id,
                autor_id=usuario.id,
                tipo=tipo,
                descricao=descricao,
                created_at=self._agora(),
            )
            self.db.add(ocorrencia)
            self.db.flush()
            self._auditar(usuario, pedido, "REGISTRO_OCORRENCIA", {
                "ocorrencia_id": str(ocorrencia.id),
                "tipo": tipo.value,
                "descricao": descricao,
            })
        return ocorrencia

    def resolver_ocorrencia(
        self,
        usuario: User,
        pedido_id: UUID,
        ocorrencia_id: UUID,
        *,
        descricao_resolucao: str,
    ) -> Ocorrencia:
        """Registra a correcao feita. Quem executa a demanda (tecnico responsavel
        ou ADMIN) resolve; o cliente confere a correcao na homologacao."""
        self._exigir_usuario_ativo(usuario)
        descricao_resolucao = ciclo_vida.validar_texto(descricao_resolucao, "descricao da correcao", 10, 2000)

        with self._transacao():
            pedido = self._bloquear_pedido_visivel(usuario, pedido_id)
            self._exigir_equipe_operacional(usuario, pedido)
            self._bloquear_se_concluido(pedido, "resolver ocorrencias")

            ocorrencia = self.db.scalar(
                select(Ocorrencia)
                .where(Ocorrencia.id == ocorrencia_id, Ocorrencia.pedido_id == pedido.id)
                .with_for_update()
            )
            if ocorrencia is None:
                raise RecursoNaoEncontradoException("Ocorrencia nao encontrada nesta demanda.")
            if ocorrencia.resolvida:
                raise OperacaoConflitanteException("A ocorrencia ja foi resolvida.")

            ocorrencia.resolvida_em = self._agora()
            ocorrencia.resolvida_por_id = usuario.id
            ocorrencia.descricao_resolucao = descricao_resolucao
            self.db.flush()
            self._auditar(usuario, pedido, "RESOLUCAO_OCORRENCIA", {
                "ocorrencia_id": str(ocorrencia.id),
                "tipo": ocorrencia.tipo.value,
                "descricao_resolucao": descricao_resolucao,
            })
        return ocorrencia

    def _contar_ocorrencias_abertas(self, pedido_id: UUID) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(Ocorrencia)
            .where(Ocorrencia.pedido_id == pedido_id, Ocorrencia.resolvida_em.is_(None))
        ) or 0

    def registrar_evidencia(
        self,
        usuario: User,
        pedido_id: UUID,
        *,
        nome_arquivo: str,
        conteudo: bytes,
        content_type: str | None = None,
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
                    raise RecursoNaoEncontradoException("Ocorrencia nao encontrada nesta demanda.")
        except Exception:
            self.db.rollback()
            raise

        try:
            return self.anexo_service.criar(
                pedido_id=pedido.id,
                enviado_por_id=usuario.id,
                nome_arquivo=nome_arquivo,
                conteudo=conteudo,
                content_type=content_type,
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

            if self._storage_settings is None:
                self._anexo_service = AnexoService(self.db)
            else:
                from app.infrastructure.storage.supabase_storage import SupabaseStorage
                self._anexo_service = AnexoService(self.db, storage=SupabaseStorage(
                    configured_settings=self._storage_settings,
                ))
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

    # As regras de perfil/vinculo moram em regras.autorizacao (SCRUM-95);
    # os atalhos abaixo so mantem a leitura do service curta.
    _exigir_usuario_ativo = staticmethod(autorizacao.exigir_usuario_ativo)
    _exigir_perfil = staticmethod(autorizacao.exigir_perfil)
    _is_admin = staticmethod(autorizacao.is_admin)
    _is_cliente_dono = staticmethod(autorizacao.is_cliente_dono)
    _is_responsavel = staticmethod(autorizacao.is_responsavel)
    _exigir_equipe_operacional = staticmethod(autorizacao.exigir_equipe_operacional)

    def _bloquear_pedido_visivel(self, usuario: User, pedido_id: UUID) -> Pedido:
        """Carrega o pedido com bloqueio de linha e aplica o escopo de leitura."""
        pedido = self.db.scalar(
            select(Pedido)
            .where(Pedido.id == pedido_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if pedido is None or not autorizacao.pode_ver(usuario, pedido):
            raise RecursoNaoEncontradoException("Demanda nao encontrada.")
        return pedido

    @staticmethod
    def _bloquear_se_concluido(pedido: Pedido, operacao: str) -> None:
        if pedido.status == StatusPedidoEnum.CONCLUIDO:
            raise RegistroImutavelException(
                f"Demandas CONCLUIDAS sao imutaveis: nao e permitido {operacao}."
            )

    def _obter_usuario_com_perfil(self, usuario_id: UUID, perfil: PerfilEnum, papel: str) -> User:
        alvo = self.users.get_by_id(usuario_id)
        if alvo is None or alvo.ativo is not True or alvo.perfil != perfil:
            raise RecursoNaoEncontradoException(f"O {papel} informado nao existe ou nao e um {perfil.value} ativo.")
        return alvo

    def _recalcular_progresso(self, pedido: Pedido, etapas: Sequence[EtapaOperacional] | None = None) -> None:
        if etapas is None:
            self.db.flush()
            etapas = self.etapas.get_by_pedido(pedido.id)
        concluidas = sum(1 for etapa in etapas if etapa.concluida)
        pedido.percentual_progresso = ciclo_vida.calcular_progresso(pedido.status, len(etapas), concluidas)

    def _registrar_historico(
        self,
        usuario: User,
        pedido: Pedido,
        status_anterior: StatusPedidoEnum,
        status_novo: StatusPedidoEnum,
    ) -> None:
        self.db.add(HistoricoStatusPedido(
            pedido_id=pedido.id,
            usuario_id=usuario.id,
            status_anterior=status_anterior,
            status_novo=status_novo,
            created_at=self._agora(),
        ))

    def _auditar(self, usuario: User, pedido: Pedido, acao: str, detalhes: dict[str, Any]) -> None:
        self.db.add(AuditoriaLog(
            usuario_id=usuario.id,
            pedido_id=pedido.id,
            acao=acao,
            detalhes=detalhes,
            created_at=self._agora(),
        ))
        self.db.flush()
