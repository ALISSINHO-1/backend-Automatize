from enum import Enum

class StatusPedidoEnum(str, Enum):
    PLANEAMENTO = "PLANEAMENTO"
    EXECUCAO = "EXECUCAO"
    HOMOLOGACAO = "HOMOLOGACAO"
    CONCLUIDO = "CONCLUIDO"

class TipoOcorrenciaEnum(str, Enum):
    AJUSTE = "AJUSTE"
    PROBLEMA = "PROBLEMA"
    DUVIDA = "DUVIDA"

class PerfilUsuarioEnum(str, Enum):
    ADMIN = "ADMIN"
    PARCEIRO = "PARCEIRO"
    CLIENTE = "CLIENTE"
