from datetime import datetime
from typing import Optional, Dict, List, Any
from app.domain.enums import StatusDemandaEnum
from app.domain.models.demanda import Demanda
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    AprovacaoNaoAutorizadaException
)

class DemandService:
    """Camada de servico com regras de negocio e maquina de estados para demandas."""

    PROGRESSO_POR_ESTADO: Dict[StatusDemandaEnum, float] = {
        StatusDemandaEnum.PLANEAMENTO: 15.0,
        StatusDemandaEnum.EXECUCAO: 50.0,
        StatusDemandaEnum.HOMOLOGACAO: 85.0,
        StatusDemandaEnum.CONCLUIDO: 100.0,
    }

    TRANSICOES_VALIDAS = {
        StatusDemandaEnum.PLANEAMENTO: [StatusDemandaEnum.EXECUCAO],
        StatusDemandaEnum.EXECUCAO: [StatusDemandaEnum.HOMOLOGACAO],
        StatusDemandaEnum.HOMOLOGACAO: [StatusDemandaEnum.CONCLUIDO, StatusDemandaEnum.EXECUCAO],
        StatusDemandaEnum.CONCLUIDO: []
    }

    _demandas: Dict[int, Demanda] = {}
    _contador_id: int = 1

    @classmethod
    def calculate_progress(cls, status: StatusDemandaEnum) -> float:
        """Calcula percentual de progresso conforme o estado."""
        return cls.PROGRESSO_POR_ESTADO.get(status, 0.0)

    @classmethod
    def create(cls, titulo: str, descricao: str, cliente_id: str) -> Demanda:
        """Cria demanda com validacoes obrigatorias."""
        if not titulo or len(titulo.strip()) < 3:
            raise RegraNegocioException("O titulo da demanda deve ter no minimo 3 caracteres.")
        if not descricao or len(descricao.strip()) < 5:
            raise RegraNegocioException("A descricao da demanda deve ter no minimo 5 caracteres.")
        if not cliente_id or not cliente_id.strip():
            raise RegraNegocioException("O cliente_id e obrigatorio.")

        demanda = Demanda(
            id=cls._contador_id,
            titulo=titulo.strip(),
            descricao=descricao.strip(),
            cliente_id=cliente_id.strip(),
            status=StatusDemandaEnum.PLANEAMENTO,
            percentual_progresso=cls.calculate_progress(StatusDemandaEnum.PLANEAMENTO)
        )

        demanda.adicionar_historico(
            acao="CRIACAO_DEMANDA",
            status_anterior="NENHUM",
            novo_status=demanda.status.value
        )

        cls._demandas[demanda.id] = demanda
        cls._contador_id += 1
        return demanda

    @classmethod
    def change_status(
        cls,
        demanda_id: int,
        novo_status: StatusDemandaEnum,
        motivo_regresso: Optional[str] = None
    ) -> Demanda:
        """Altera estado com maquina de estados e grava historico."""
        demanda = cls._demandas.get(demanda_id)
        if not demanda:
            raise RegraNegocioException(f"Demanda #{demanda_id} nao encontrada.")

        status_atual = demanda.status

        if status_atual == StatusDemandaEnum.CONCLUIDO:
            raise TransicaoEstadoInvalidaException("Demandas no estado CONCLUIDO sao imutaveis.")

        transicoes_permitidas = cls.TRANSICOES_VALIDAS.get(status_atual, [])
        if novo_status not in transicoes_permitidas:
            raise TransicaoEstadoInvalidaException(
                f"Transicao ilegal: nao e permitido transitar de {status_atual.value} para {novo_status.value}."
            )

        if status_atual == StatusDemandaEnum.HOMOLOGACAO and novo_status == StatusDemandaEnum.EXECUCAO:
            if not motivo_regresso or len(motivo_regresso.strip()) < 10:
                raise TransicaoEstadoInvalidaException(
                    "O regresso de HOMOLOGACAO para EXECUCAO exige a descricao do motivo com no minimo 10 caracteres."
                )

        demanda.status = novo_status
        demanda.percentual_progresso = cls.calculate_progress(novo_status)
        demanda.adicionar_historico(
            acao="ALTERACAO_ESTADO",
            status_anterior=status_atual.value,
            novo_status=novo_status.value,
            motivo=motivo_regresso
        )
        return demanda

    @classmethod
    def aprovar_homologacao(cls, demanda_id: int, cliente_id: str) -> Demanda:
        """Aprovacao formal somente em HOMOLOGACAO -> CONCLUIDO."""
        demanda = cls._demandas.get(demanda_id)
        if not demanda:
            raise RegraNegocioException(f"Demanda #{demanda_id} nao encontrada.")

        if demanda.status != StatusDemandaEnum.HOMOLOGACAO:
            raise AprovacaoNaoAutorizadaException(
                f"Apenas demandas em HOMOLOGACAO podem ser aprovadas. Estado atual: {demanda.status.value}."
            )

        if not cliente_id or not cliente_id.strip():
            raise AprovacaoNaoAutorizadaException("A identificacao do cliente e obrigatoria para homologacao.")

        demanda.status = StatusDemandaEnum.CONCLUIDO
        demanda.percentual_progresso = cls.calculate_progress(StatusDemandaEnum.CONCLUIDO)
        demanda.aprovado_por = cliente_id.strip()
        demanda.data_aprovacao = datetime.now()

        demanda.adicionar_historico(
            acao="ACEITE_FORMAL_HOMOLOGACAO",
            status_anterior=StatusDemandaEnum.HOMOLOGACAO.value,
            novo_status=StatusDemandaEnum.CONCLUIDO.value,
            motivo=f"Aprovado formalmente por {cliente_id}"
        )
        return demanda

    @classmethod
    def rejeitar_homologacao(cls, demanda_id: int, motivo_rejeicao: str) -> Demanda:
        demanda = cls._demandas.get(demanda_id)
        if not demanda:
            raise RegraNegocioException(f"Demanda #{demanda_id} nao encontrada.")

        if demanda.status != StatusDemandaEnum.HOMOLOGACAO:
            raise TransicaoEstadoInvalidaException(
                f"Apenas demandas em HOMOLOGACAO podem ser rejeitadas. Estado atual: {demanda.status.value}."
            )

        if not motivo_rejeicao or len(motivo_rejeicao.strip()) < 10:
            raise TransicaoEstadoInvalidaException(
                "A rejeicao da homologacao exige um motivo detalhado com no minimo 10 caracteres."
            )

        demanda.status = StatusDemandaEnum.EXECUCAO
        demanda.percentual_progresso = cls.calculate_progress(StatusDemandaEnum.EXECUCAO)

        demanda.adicionar_historico(
            acao="REJEICAO_HOMOLOGACAO",
            status_anterior=StatusDemandaEnum.HOMOLOGACAO.value,
            novo_status=StatusDemandaEnum.EXECUCAO.value,
            motivo=motivo_rejeicao.strip()
        )
        return demanda

    @classmethod
    def get_by_id(cls, demanda_id: int) -> Optional[Demanda]:
        return cls._demandas.get(demanda_id)

    @classmethod
    def list_all(cls) -> List[Demanda]:
        return list(cls._demandas.values())