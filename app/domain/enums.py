from enum import Enum

class StatusDemandaEnum(str, Enum):
    PLANEAMENTO = "PLANEAMENTO"
    EXECUCAO = "EXECUCAO"
    HOMOLOGACAO = "HOMOLOGACAO"
    CONCLUIDO = "CONCLUIDO"

# Alias de compatibilidade com pedidos
StatusPedidoEnum = StatusDemandaEnum

class TipoOcorrenciaEnum(str, Enum):
    AJUSTE = "AJUSTE"
    PROBLEMA = "PROBLEMA"
    DUVIDA = "DUVIDA"

class PerfilUsuarioEnum(str, Enum):
    ADMIN = "ADMIN"
    PARCEIRO = "PARCEIRO"
    CLIENTE = "CLIENTE"