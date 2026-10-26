from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.enums import StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.domain.regras import ciclo_vida
from app.core.exceptions import RegistroImutavelException, TransicaoEstadoInvalidaException
from app.repositories.etapa_operacional_repository import EtapaOperacionalRepository
from app.repositories.historico_status_pedido_repository import (
    HistoricoStatusPedidoRepository,
)
from app.repositories.pedido_repository import PedidoRepository
from app.schemas.pedido import PedidoCreate, PedidoUpdate


class PedidoNaoEncontradoError(Exception):
    pass


class CodigoPedidoDuplicadoError(Exception):
    pass


class PedidoService:
    """Service responsável pelas regras e operações relacionadas aos pedidos."""

    def __init__(
        self,
        db: Session,
        repository: PedidoRepository | None = None,
        historico_repository: HistoricoStatusPedidoRepository | None = None,
        etapas_repository: EtapaOperacionalRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or PedidoRepository(db)
        self.historico_repository = (
            historico_repository
            if historico_repository is not None
            else HistoricoStatusPedidoRepository(db)
        )
        self.etapas_repository = etapas_repository or EtapaOperacionalRepository(db)

    # ------------------------------------------------------------------
    # Regras de ciclo de vida (implementadas em app.domain.regras.ciclo_vida)
    # ------------------------------------------------------------------

    @classmethod
    def calcular_progresso(cls, status: StatusPedidoEnum) -> float:
        """Percentual de progresso padrão do status (sem considerar etapas)."""
        return float(ciclo_vida.calcular_progresso(status))

    @classmethod
    def validar_e_transitar(
        cls,
        status_atual: StatusPedidoEnum,
        novo_status: StatusPedidoEnum,
        motivo_regresso: Optional[str] = None,
        *,
        total_etapas: int = 0,
        etapas_pendentes: tuple[str, ...] = (),
    ) -> float:
        """
        Valida uma transição pela máquina de estados e devolve o novo progresso.

        A conclusão não é permitida aqui: ela exige aceite formal
        (AprovacaoService / DemandService.aprovar_homologacao).
        """
        ciclo_vida.validar_transicao(
            status_atual,
            novo_status,
            total_etapas=total_etapas,
            etapas_pendentes=etapas_pendentes,
            motivo_regresso=motivo_regresso,
        )
        return cls.calcular_progresso(novo_status)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def listar(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Pedido]:
        return self.repository.get_all(
            offset=offset,
            limit=limit,
        )

    def buscar_por_id(
        self,
        pedido_id: UUID,
    ) -> Pedido:
        pedido = self.repository.get_by_id(pedido_id)

        if pedido is None:
            raise PedidoNaoEncontradoError(
                f"Pedido {pedido_id} não encontrado."
            )

        return pedido

    def buscar_por_codigo(
        self,
        codigo: str,
    ) -> Pedido:
        pedido = self.repository.get_by_codigo(codigo)

        if pedido is None:
            raise PedidoNaoEncontradoError(
                f"Pedido '{codigo}' não encontrado."
            )

        return pedido

    # ------------------------------------------------------------------
    # Criação
    # ------------------------------------------------------------------

    def criar(
        self,
        dados: PedidoCreate,
    ) -> Pedido:
        pedido_existente = self.repository.get_by_codigo(
            dados.codigo_identificador
        )

        if pedido_existente is not None:
            raise CodigoPedidoDuplicadoError(
                "Já existe um pedido com o código "
                f"'{dados.codigo_identificador}'."
            )

        try:
            pedido = self.repository.create(
                dados.model_dump()
            )

            self.db.commit()
            self.db.refresh(pedido)

            return pedido

        except IntegrityError:
            self.db.rollback()
            raise

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Atualização
    # ------------------------------------------------------------------

    def atualizar(
        self,
        pedido_id: UUID,
        dados: PedidoUpdate,
        usuario_id: UUID | None = None,
    ) -> Pedido:
        pedido = self.buscar_por_id(pedido_id)

        status_anterior = pedido.status

        dados_atualizacao = dados.model_dump(
            exclude_unset=True
        )

        try:
            if status_anterior == StatusPedidoEnum.CONCLUIDO:
                raise RegistroImutavelException("Demandas CONCLUIDAS sao imutaveis.")

            novo_status = dados_atualizacao.get("status")
            mudou_status = novo_status is not None and novo_status != status_anterior
            if mudou_status and usuario_id is None:
                raise ValueError("usuario_id é obrigatório para alteração de status.")

            if mudou_status:
                # Mesmas regras do DemandService.alterar_status: sem isso a edição
                # genérica deixaria pular estados, homologar com etapas pendentes
                # ou voltar para EXECUCAO sem a rejeição (e o motivo) do cliente.
                if (
                    status_anterior == StatusPedidoEnum.HOMOLOGACAO
                    and novo_status == StatusPedidoEnum.EXECUCAO
                ):
                    raise TransicaoEstadoInvalidaException(
                        "O retorno de HOMOLOGACAO para EXECUCAO e feito pela rejeicao do cliente."
                    )
                etapas = self.etapas_repository.get_by_pedido(pedido.id)
                ciclo_vida.validar_transicao(
                    status_anterior,
                    novo_status,
                    total_etapas=len(etapas),
                    etapas_pendentes=tuple(e.descricao for e in etapas if not e.concluida),
                )
                # O progresso acompanha o estado; um percentual enviado junto seria inconsistente.
                dados_atualizacao["percentual_progresso"] = ciclo_vida.calcular_progresso(
                    novo_status,
                    len(etapas),
                    sum(1 for e in etapas if e.concluida),
                )

            pedido = self.repository.update(
                pedido,
                dados_atualizacao,
            )

            if mudou_status:
                self.historico_repository.create(
                    {
                        "pedido_id": pedido.id,
                        "status_anterior": status_anterior,
                        "status_novo": novo_status,
                        "usuario_id": usuario_id,
                    }
                )

            self.db.commit()
            self.db.refresh(pedido)

            return pedido

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Exclusão
    # ------------------------------------------------------------------

    def excluir(
        self,
        pedido_id: UUID,
    ) -> None:
        pedido = self.buscar_por_id(pedido_id)

        try:
            self.repository.delete(pedido)

            self.db.commit()

        except Exception:
            self.db.rollback()
            raise
