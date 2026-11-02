from app.core.exceptions import AcessoNegadoException, RecursoNaoEncontradoException
from app.domain.models.enums import PerfilEnum
from app.repositories.user_repository import UserRepository


class UserQueryService:
    def __init__(self, db):
        self.users = UserRepository(db)

    @staticmethod
    def _require(user, profile):
        if user.ativo is not True or user.perfil != profile:
            raise AcessoNegadoException("Perfil sem permissao para esta consulta.")

    def technicians(self, user, *, offset=0, limit=100):
        self._require(user, PerfilEnum.ADMIN)
        return self.users.list_tecnicos(offset=offset, limit=limit)

    def clients(self, user, *, offset=0, limit=100):
        self._require(user, PerfilEnum.TECNICO)
        return self.users.list_clientes_por_responsavel(
            responsavel_id=user.id, offset=offset, limit=limit,
        )

    def client(self, user, client_id):
        self._require(user, PerfilEnum.TECNICO)
        result = self.users.get_cliente_por_responsavel(client_id, responsavel_id=user.id)
        if result is None:
            raise RecursoNaoEncontradoException("Cliente nao encontrado.")
        return result
