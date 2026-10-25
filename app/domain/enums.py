"""Compatibilidade: os enums oficiais sao os persistidos em app.domain.models.enums.

Este modulo existia com valores divergentes (TipoOcorrenciaEnum, PerfilUsuarioEnum);
agora apenas reexporta os enums do banco para que imports antigos continuem validos.
"""
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum, TipoOcorrenciaEnum

StatusDemandaEnum = StatusPedidoEnum
PerfilUsuarioEnum = PerfilEnum

__all__ = [
    "PerfilEnum",
    "PerfilUsuarioEnum",
    "StatusDemandaEnum",
    "StatusPedidoEnum",
    "TipoOcorrenciaEnum",
]
