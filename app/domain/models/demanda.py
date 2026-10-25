import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Optional, List, Mapping, Any, Tuple
from app.domain.enums import StatusDemandaEnum
from app.core.exceptions import RegistroImutavelException


@dataclass(frozen=True)
class RegistroAceite:
    """Aceite formal da homologacao. Imutavel apos criado."""

    demanda_id: int
    cliente_id: str
    data_hora: datetime
    hash_validacao: str

    @staticmethod
    def gerar_hash(demanda_id: int, cliente_id: str, data_hora: datetime) -> str:
        conteudo = f"{demanda_id}|{cliente_id}|{data_hora.isoformat()}"
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

    @classmethod
    def criar(cls, demanda_id: int, cliente_id: str) -> "RegistroAceite":
        data_hora = datetime.now(timezone.utc)
        return cls(
            demanda_id=demanda_id,
            cliente_id=cliente_id,
            data_hora=data_hora,
            hash_validacao=cls.gerar_hash(demanda_id, cliente_id, data_hora),
        )

    def is_integro(self) -> bool:
        """Confere se os dados do aceite ainda correspondem ao hash gravado."""
        return self.hash_validacao == self.gerar_hash(self.demanda_id, self.cliente_id, self.data_hora)


@dataclass
class EtapaOperacional:
    """Etapa operacional da execucao que precisa ser concluida antes da homologacao."""

    id: int
    descricao: str
    concluida: bool = False
    concluida_em: Optional[datetime] = None


@dataclass(frozen=True)
class Evidencia:
    """Anexo ou captura de tela vinculado a demanda ou a uma ocorrencia."""

    nome_arquivo: str
    extensao: str
    tamanho_bytes: int
    enviado_por: str
    enviado_em: datetime
    ocorrencia_id: Optional[str] = None


class Demanda:

    def __init__(
        self,
        id: int,
        titulo: str,
        descricao: str,
        cliente_id: str,
        status: StatusDemandaEnum = StatusDemandaEnum.PLANEAMENTO,
        percentual_progresso: float = 15.0,
        criado_em: Optional[datetime] = None
    ):
        self.id = id
        self.titulo = titulo
        self.descricao = descricao
        self.cliente_id = cliente_id
        self.status = status
        self.percentual_progresso = percentual_progresso
        self.criado_em = criado_em or datetime.now()
        self.responsavel_id: Optional[str] = None
        self._aceite: Optional[RegistroAceite] = None
        self._historico: List[Mapping[str, Any]] = []
        self._etapas: List[EtapaOperacional] = []
        self._evidencias: List[Evidencia] = []

    @property
    def etapas(self) -> Tuple[EtapaOperacional, ...]:
        return tuple(self._etapas)

    @property
    def etapas_pendentes(self) -> Tuple[EtapaOperacional, ...]:
        return tuple(etapa for etapa in self._etapas if not etapa.concluida)

    @property
    def evidencias(self) -> Tuple[Evidencia, ...]:
        return tuple(self._evidencias)

    def adicionar_etapa(self, descricao: str) -> EtapaOperacional:
        etapa = EtapaOperacional(id=len(self._etapas) + 1, descricao=descricao)
        self._etapas.append(etapa)
        return etapa

    def obter_etapa(self, etapa_id: int) -> Optional[EtapaOperacional]:
        return next((etapa for etapa in self._etapas if etapa.id == etapa_id), None)

    def adicionar_evidencia(self, evidencia: Evidencia):
        self._evidencias.append(evidencia)

    @property
    def aceite(self) -> Optional[RegistroAceite]:
        return self._aceite

    @property
    def aprovado_por(self) -> Optional[str]:
        return self._aceite.cliente_id if self._aceite else None

    @property
    def data_aprovacao(self) -> Optional[datetime]:
        return self._aceite.data_hora if self._aceite else None

    @property
    def historico_alteracoes(self) -> Tuple[Mapping[str, Any], ...]:
        """Historico somente leitura: entradas nao podem ser removidas nem editadas."""
        return tuple(self._historico)

    def registrar_aceite(self, aceite: RegistroAceite):
        if self._aceite is not None:
            raise RegistroImutavelException(
                f"A demanda #{self.id} ja possui aceite formal registrado e ele nao pode ser alterado."
            )
        self._aceite = aceite

    def adicionar_historico(
        self,
        acao: str,
        status_anterior: str,
        novo_status: str,
        motivo: Optional[str] = None,
        autor_id: Optional[str] = None,
        detalhes: Optional[Mapping[str, Any]] = None
    ):
        self._historico.append(MappingProxyType({
            "data_hora": datetime.now(timezone.utc),
            "acao": acao,
            "autor_id": autor_id,
            "status_anterior": status_anterior,
            "novo_status": novo_status,
            "motivo": motivo,
            "detalhes": MappingProxyType(dict(detalhes or {}))
        }))
