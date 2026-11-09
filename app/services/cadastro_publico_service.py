"""Registro desabilitado por padrao; nunca cria ADMIN/TECNICO nem contrato."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User

class CadastroPublicoService:
    def __init__(self, db: Session):
        self.db = db

    def solicitar(self, *, nome: str, email: str, senha: str) -> None:
        # Executar hash mesmo para emails existentes reduz a diferenca temporal.
        hashed = hash_password(senha)
        try:
            existente = self.db.scalar(select(User.id).where(func.lower(User.email) == email))
            if existente is not None:
                return
            self.db.add(User(
                nome=nome,
                email=email,
                senha_hash=hashed,
                perfil=PerfilEnum.CLIENTE,
                situacao_cadastro="PENDENTE",
                ativo=True,
            ))
            self.db.commit()
        except IntegrityError:
            # Uma criacao simultanea do mesmo e-mail tem retorno identico.
            self.db.rollback()
        except Exception:
            self.db.rollback()
            raise
