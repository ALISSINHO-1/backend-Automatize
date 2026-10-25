import os
from datetime import datetime, timezone
from typing import Optional, Dict, List
from app.domain.enums import StatusDemandaEnum
from app.domain.models.demanda import Demanda, RegistroAceite, EtapaOperacional, Evidencia
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    AprovacaoNaoAutorizadaException,
    RegistroImutavelException
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

    EXTENSOES_EVIDENCIA_PERMITIDAS = frozenset({"png", "jpg", "jpeg", "pdf"})
    TAMANHO_MAXIMO_EVIDENCIA_BYTES = 10 * 1024 * 1024

    _demandas: Dict[int, Demanda] = {}
    _contador_id: int = 1

    @classmethod
    def calculate_progress(cls, status: StatusDemandaEnum) -> float:
        """Calcula percentual de progresso conforme o estado."""
        return cls.PROGRESSO_POR_ESTADO.get(status, 0.0)

    @classmethod
    def calcular_progresso_demanda(cls, demanda: Demanda) -> float:
        """Em EXECUCAO com etapas cadastradas, o progresso avanca de PLANEAMENTO ate HOMOLOGACAO
        proporcionalmente as etapas concluidas. Nos demais casos vale o percentual do estado."""
        if demanda.status != StatusDemandaEnum.EXECUCAO or not demanda.etapas:
            return cls.calculate_progress(demanda.status)

        inicio = cls.PROGRESSO_POR_ESTADO[StatusDemandaEnum.PLANEAMENTO]
        fim = cls.PROGRESSO_POR_ESTADO[StatusDemandaEnum.HOMOLOGACAO]
        concluidas = len(demanda.etapas) - len(demanda.etapas_pendentes)
        return round(inicio + (fim - inicio) * concluidas / len(demanda.etapas), 2)

    @classmethod
    def _obter_demanda(cls, demanda_id: int) -> Demanda:
        demanda = cls._demandas.get(demanda_id)
        if not demanda:
            raise RegraNegocioException(f"Demanda #{demanda_id} nao encontrada.")
        return demanda

    @staticmethod
    def _bloquear_se_concluida(demanda: Demanda, operacao: str):
        if demanda.status == StatusDemandaEnum.CONCLUIDO:
            raise RegistroImutavelException(
                f"Demandas CONCLUIDAS sao imutaveis: nao e permitido {operacao}."
            )

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
            novo_status=demanda.status.value,
            autor_id=demanda.cliente_id
        )

        cls._demandas[demanda.id] = demanda
        cls._contador_id += 1
        return demanda

    @classmethod
    def update(
        cls,
        demanda_id: int,
        titulo: str,
        descricao: str,
        autor_id: Optional[str] = None
    ) -> Demanda:
        """Edita titulo e descricao com as mesmas validacoes do cadastro."""
        demanda = cls._obter_demanda(demanda_id)
        cls._bloquear_se_concluida(demanda, "editar a demanda")

        if not titulo or len(titulo.strip()) < 3:
            raise RegraNegocioException("O titulo da demanda deve ter no minimo 3 caracteres.")
        if not descricao or len(descricao.strip()) < 5:
            raise RegraNegocioException("A descricao da demanda deve ter no minimo 5 caracteres.")

        anterior = {"titulo": demanda.titulo, "descricao": demanda.descricao}
        demanda.titulo = titulo.strip()
        demanda.descricao = descricao.strip()

        demanda.adicionar_historico(
            acao="EDICAO_DEMANDA",
            status_anterior=demanda.status.value,
            novo_status=demanda.status.value,
            autor_id=autor_id,
            detalhes={"anterior": anterior, "novo": {"titulo": demanda.titulo, "descricao": demanda.descricao}}
        )
        return demanda

    @classmethod
    def change_status(
        cls,
        demanda_id: int,
        novo_status: StatusDemandaEnum,
        motivo_regresso: Optional[str] = None,
        autor_id: Optional[str] = None
    ) -> Demanda:
        """Altera estado com maquina de estados e grava historico."""
        demanda = cls._obter_demanda(demanda_id)

        status_atual = demanda.status

        if status_atual == StatusDemandaEnum.CONCLUIDO:
            raise TransicaoEstadoInvalidaException("Demandas no estado CONCLUIDO sao imutaveis.")

        transicoes_permitidas = cls.TRANSICOES_VALIDAS.get(status_atual, [])
        if novo_status not in transicoes_permitidas:
            raise TransicaoEstadoInvalidaException(
                f"Transicao ilegal: nao e permitido transitar de {status_atual.value} para {novo_status.value}."
            )

        if novo_status == StatusDemandaEnum.CONCLUIDO:
            raise AprovacaoNaoAutorizadaException(
                "A conclusao exige aceite formal do cliente. Utilize a aprovacao da homologacao."
            )

        if status_atual == StatusDemandaEnum.HOMOLOGACAO and novo_status == StatusDemandaEnum.EXECUCAO:
            if not motivo_regresso or len(motivo_regresso.strip()) < 10:
                raise TransicaoEstadoInvalidaException(
                    "O regresso de HOMOLOGACAO para EXECUCAO exige a descricao do motivo com no minimo 10 caracteres."
                )

        if novo_status == StatusDemandaEnum.HOMOLOGACAO and demanda.etapas_pendentes:
            pendentes = ", ".join(f"#{etapa.id} {etapa.descricao}" for etapa in demanda.etapas_pendentes)
            raise TransicaoEstadoInvalidaException(
                f"Nao e permitido enviar para HOMOLOGACAO com etapas operacionais pendentes: {pendentes}."
            )

        demanda.status = novo_status
        demanda.percentual_progresso = cls.calcular_progresso_demanda(demanda)
        demanda.adicionar_historico(
            acao="ALTERACAO_ESTADO",
            status_anterior=status_atual.value,
            novo_status=novo_status.value,
            motivo=motivo_regresso,
            autor_id=autor_id
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

        demanda.registrar_aceite(RegistroAceite.criar(demanda.id, cliente_id.strip()))
        demanda.status = StatusDemandaEnum.CONCLUIDO
        demanda.percentual_progresso = cls.calculate_progress(StatusDemandaEnum.CONCLUIDO)

        demanda.adicionar_historico(
            acao="ACEITE_FORMAL_HOMOLOGACAO",
            status_anterior=StatusDemandaEnum.HOMOLOGACAO.value,
            novo_status=StatusDemandaEnum.CONCLUIDO.value,
            motivo=f"Aprovado formalmente por {cliente_id}",
            autor_id=demanda.aprovado_por
        )
        return demanda

    @classmethod
    def rejeitar_homologacao(cls, demanda_id: int, motivo_rejeicao: str, autor_id: Optional[str] = None) -> Demanda:
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
        demanda.percentual_progresso = cls.calcular_progresso_demanda(demanda)

        demanda.adicionar_historico(
            acao="REJEICAO_HOMOLOGACAO",
            status_anterior=StatusDemandaEnum.HOMOLOGACAO.value,
            novo_status=StatusDemandaEnum.EXECUCAO.value,
            motivo=motivo_rejeicao.strip(),
            autor_id=autor_id
        )
        return demanda

    @classmethod
    def adicionar_etapa(cls, demanda_id: int, descricao: str, autor_id: Optional[str] = None) -> EtapaOperacional:
        """Cadastra etapa operacional enquanto a demanda esta em PLANEAMENTO ou EXECUCAO."""
        demanda = cls._obter_demanda(demanda_id)
        if demanda.status not in (StatusDemandaEnum.PLANEAMENTO, StatusDemandaEnum.EXECUCAO):
            raise TransicaoEstadoInvalidaException(
                f"Etapas so podem ser adicionadas em PLANEAMENTO ou EXECUCAO. Estado atual: {demanda.status.value}."
            )
        if not descricao or len(descricao.strip()) < 3:
            raise RegraNegocioException("A descricao da etapa deve ter no minimo 3 caracteres.")

        etapa = demanda.adicionar_etapa(descricao.strip())
        demanda.percentual_progresso = cls.calcular_progresso_demanda(demanda)
        demanda.adicionar_historico(
            acao="CADASTRO_ETAPA",
            status_anterior=demanda.status.value,
            novo_status=demanda.status.value,
            autor_id=autor_id,
            detalhes={"etapa_id": etapa.id, "descricao": etapa.descricao}
        )
        return etapa

    @classmethod
    def concluir_etapa(cls, demanda_id: int, etapa_id: int, autor_id: Optional[str] = None) -> EtapaOperacional:
        """Conclui etapa operacional; permitido somente durante a EXECUCAO."""
        demanda = cls._obter_demanda(demanda_id)
        if demanda.status != StatusDemandaEnum.EXECUCAO:
            raise TransicaoEstadoInvalidaException(
                f"Etapas so podem ser concluidas em EXECUCAO. Estado atual: {demanda.status.value}."
            )

        etapa = demanda.obter_etapa(etapa_id)
        if not etapa:
            raise RegraNegocioException(f"Etapa #{etapa_id} nao encontrada na demanda #{demanda_id}.")
        if etapa.concluida:
            raise RegraNegocioException(f"A etapa #{etapa_id} ja esta concluida.")

        etapa.concluida = True
        etapa.concluida_em = datetime.now(timezone.utc)
        demanda.percentual_progresso = cls.calcular_progresso_demanda(demanda)
        demanda.adicionar_historico(
            acao="CONCLUSAO_ETAPA",
            status_anterior=demanda.status.value,
            novo_status=demanda.status.value,
            autor_id=autor_id,
            detalhes={"etapa_id": etapa.id, "descricao": etapa.descricao}
        )
        return etapa

    @classmethod
    def atribuir_responsavel(cls, demanda_id: int, responsavel_id: str, autor_id: Optional[str] = None) -> Demanda:
        """Atribui o responsavel tecnico e audita a atribuicao."""
        demanda = cls._obter_demanda(demanda_id)
        cls._bloquear_se_concluida(demanda, "alterar o responsavel")
        if not responsavel_id or not responsavel_id.strip():
            raise RegraNegocioException("O responsavel_id e obrigatorio.")

        anterior = demanda.responsavel_id
        demanda.responsavel_id = responsavel_id.strip()
        demanda.adicionar_historico(
            acao="ATRIBUICAO_RESPONSAVEL",
            status_anterior=demanda.status.value,
            novo_status=demanda.status.value,
            autor_id=autor_id,
            detalhes={"responsavel_anterior": anterior, "responsavel_novo": demanda.responsavel_id}
        )
        return demanda

    @classmethod
    def registrar_evidencia(
        cls,
        demanda_id: int,
        nome_arquivo: str,
        tamanho_bytes: int,
        autor_id: str,
        ocorrencia_id: Optional[str] = None
    ) -> Evidencia:
        """Valida extensao e tamanho do anexo, vincula a demanda e audita o envio."""
        demanda = cls._obter_demanda(demanda_id)
        cls._bloquear_se_concluida(demanda, "enviar evidencias")

        if not autor_id or not autor_id.strip():
            raise RegraNegocioException("O autor do envio da evidencia e obrigatorio.")

        nome_arquivo = os.path.basename((nome_arquivo or "").strip())
        extensao = os.path.splitext(nome_arquivo)[1].lstrip(".").lower()
        if extensao not in cls.EXTENSOES_EVIDENCIA_PERMITIDAS:
            permitidas = ", ".join(sorted(cls.EXTENSOES_EVIDENCIA_PERMITIDAS))
            raise RegraNegocioException(f"Extensao de arquivo nao permitida. Permitidas: {permitidas}.")

        if tamanho_bytes <= 0 or tamanho_bytes > cls.TAMANHO_MAXIMO_EVIDENCIA_BYTES:
            limite_mb = cls.TAMANHO_MAXIMO_EVIDENCIA_BYTES // (1024 * 1024)
            raise RegraNegocioException(f"O arquivo deve ter entre 1 byte e {limite_mb} MB.")

        evidencia = Evidencia(
            nome_arquivo=nome_arquivo,
            extensao=extensao,
            tamanho_bytes=tamanho_bytes,
            enviado_por=autor_id.strip(),
            enviado_em=datetime.now(timezone.utc),
            ocorrencia_id=ocorrencia_id
        )
        demanda.adicionar_evidencia(evidencia)
        demanda.adicionar_historico(
            acao="ENVIO_EVIDENCIA",
            status_anterior=demanda.status.value,
            novo_status=demanda.status.value,
            autor_id=evidencia.enviado_por,
            detalhes={
                "nome_arquivo": evidencia.nome_arquivo,
                "tamanho_bytes": evidencia.tamanho_bytes,
                "ocorrencia_id": ocorrencia_id
            }
        )
        return evidencia

    @classmethod
    def delete(cls, demanda_id: int) -> None:
        demanda = cls._obter_demanda(demanda_id)
        cls._bloquear_se_concluida(demanda, "excluir a demanda")

        del cls._demandas[demanda_id]

    @classmethod
    def get_by_id(cls, demanda_id: int) -> Optional[Demanda]:
        return cls._demandas.get(demanda_id)

    @classmethod
    def list_all(cls) -> List[Demanda]:
        return list(cls._demandas.values())