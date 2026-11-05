"""Politica unica de autorizacao por perfil e vinculo com a demanda (SCRUM-95).

Antes cada service repetia suas proprias checagens de perfil; aqui fica a
unica fonte da regra, para leitura e escrita usarem o mesmo criterio.
Funcoes puras (sem banco): recebem o usuario autenticado e, quando
aplicavel, o pedido ja carregado.

Vinculos com a demanda:
- ADMIN: todas as demandas.
- CLIENTE: somente as demandas em que e o cliente (pedido.cliente_id).
- TECNICO: somente as demandas em que e o responsavel (pedido.responsavel_id).
"""
from uuid import UUID

from app.core.exceptions import AcessoNegadoException
from app.domain.models.enums import PerfilEnum
from app.domain.models.pedido import Pedido
from app.domain.models.user import User


def escopo_leitura(usuario: User) -> dict[str, UUID]:
    """Filtro de consulta das demandas visiveis ao usuario (vazio = todas).

    Perfis sem politica conhecida sao recusados em vez de verem tudo."""
    if usuario.perfil == PerfilEnum.ADMIN:
        return {}
    if usuario.perfil == PerfilEnum.CLIENTE:
        return {"cliente_id": usuario.id}
    if usuario.perfil == PerfilEnum.TECNICO:
        return {"responsavel_id": usuario.id}
    raise AcessoNegadoException("Perfil sem permissao para consultar demandas.")


def is_admin(usuario: User) -> bool:
    return usuario.perfil == PerfilEnum.ADMIN


def is_cliente_dono(usuario: User, pedido: Pedido) -> bool:
    return usuario.perfil == PerfilEnum.CLIENTE and pedido.cliente_id == usuario.id


def is_responsavel(usuario: User, pedido: Pedido) -> bool:
    return usuario.perfil == PerfilEnum.TECNICO and pedido.responsavel_id == usuario.id


def pode_ver(usuario: User, pedido: Pedido) -> bool:
    return is_admin(usuario) or is_cliente_dono(usuario, pedido) or is_responsavel(usuario, pedido)


def exigir_usuario_ativo(usuario: User | None) -> None:
    if usuario is None or usuario.id is None or usuario.ativo is not True:
        raise AcessoNegadoException("A operacao exige um usuario autenticado e ativo.")


def exigir_perfil(usuario: User, *perfis: PerfilEnum) -> None:
    exigir_usuario_ativo(usuario)
    if usuario.perfil not in perfis:
        raise AcessoNegadoException("Perfil sem permissao para esta operacao.")


def exigir_equipe_operacional(usuario: User, pedido: Pedido) -> None:
    """Execucao da demanda (estados, etapas, correcoes): ADMIN ou o tecnico responsavel."""
    if not is_admin(usuario) and not is_responsavel(usuario, pedido):
        raise AcessoNegadoException("Somente o tecnico responsavel ou um ADMIN pode executar esta operacao.")


def exigir_dono_ou_admin(usuario: User, pedido: Pedido, operacao: str) -> None:
    if not is_admin(usuario) and not is_cliente_dono(usuario, pedido):
        raise AcessoNegadoException(f"Somente o cliente da demanda ou um ADMIN pode {operacao}.")
