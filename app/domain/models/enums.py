from enum import Enum


class PerfilEnum(str, Enum):
    ADMIN = "ADMIN"
    CLIENTE = "CLIENTE"
    TECNICO = "TECNICO"


class StatusPedidoEnum(str, Enum):
    PLANEAMENTO = "PLANEAMENTO"
    EXECUCAO = "EXECUCAO"
    HOMOLOGACAO = "HOMOLOGACAO"
    CONCLUIDO = "CONCLUIDO"


class TipoOcorrenciaEnum(str, Enum):
    ERRO = "ERRO"
    SOLICITACAO_CORRECAO = "SOLICITACAO_CORRECAO"
    REGRESSO_ESTADO = "REGRESSO_ESTADO"