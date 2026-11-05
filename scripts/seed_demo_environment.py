"""Seed opt-in de dados DEMO; execute com --apply para persistir.

Nao aplica migrations, nao atualiza contas existentes e nao redefine senhas.
O seed legado scripts.seed_demo_user continua disponivel sem alteracoes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.core.security import hash_password, verify_password
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum, TipoOcorrenciaEnum
from app.domain.models.ocorrencia import Ocorrencia
from app.domain.models.user import User
from app.domain.schemas.auth_schema import LoginRequest
from app.repositories.base_repository import BaseRepository
from app.repositories.pedido_repository import PedidoRepository
from app.repositories.user_repository import UserRepository
from scripts.seed_demo_user import DemoUserSettings


DEMO_PEDIDO_CODIGO = "DEMO-APRESENTACAO"
DEMO_OCORRENCIA_DESCRICAO = "[DEMO] Registro de apresentacao para validar a persistencia de ocorrencias."


class DemoSeedConflictError(RuntimeError):
    """Configuracao conflita com dados existentes; nenhum dado sera sobrescrito."""


class DemoEnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )

    DEMO_ADMIN_EMAIL: str = Field(default="admin.demo@automatize.local", max_length=255)
    DEMO_ADMIN_PASSWORD: SecretStr = Field(repr=False)
    DEMO_TECNICO_EMAIL: str = Field(default="tecnico.demo@automatize.local", max_length=255)
    DEMO_TECNICO_PASSWORD: SecretStr = Field(repr=False)
    DEMO_CLIENTE_EMAIL: str = Field(default="cliente.demo@automatize.local", max_length=255)
    DEMO_CLIENTE_PASSWORD: SecretStr = Field(repr=False)

    @field_validator("DEMO_ADMIN_EMAIL", "DEMO_TECNICO_EMAIL", "DEMO_CLIENTE_EMAIL")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return LoginRequest.validate_email_shape(value.strip().lower())

    @field_validator("DEMO_ADMIN_PASSWORD", "DEMO_TECNICO_PASSWORD", "DEMO_CLIENTE_PASSWORD")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        # Reuse the normal seed's bcrypt bound, including the UTF-8 byte limit.
        return DemoUserSettings.validate_password(value)

    @model_validator(mode="after")
    def distinct_accounts(self) -> DemoEnvironmentSettings:
        if len({self.DEMO_ADMIN_EMAIL, self.DEMO_TECNICO_EMAIL, self.DEMO_CLIENTE_EMAIL}) != 3:
            raise ValueError("As tres contas DEMO devem ter e-mails diferentes.")
        return self

    def accounts(self) -> dict[PerfilEnum, DemoUserSettings]:
        return {
            perfil: DemoUserSettings(
                _env_file=None,
                DEMO_USER_NAME=f"{perfil.value.title()} DEMO",
                DEMO_USER_EMAIL=getattr(self, f"DEMO_{perfil.value}_EMAIL"),
                DEMO_USER_PASSWORD=getattr(self, f"DEMO_{perfil.value}_PASSWORD"),
            )
            for perfil in (PerfilEnum.ADMIN, PerfilEnum.TECNICO, PerfilEnum.CLIENTE)
        }


@dataclass(frozen=True)
class DemoSeedResult:
    user_ids: dict[PerfilEnum, UUID]
    created_profiles: tuple[PerfilEnum, ...]
    pedido_id: UUID
    ocorrencia_id: UUID
    pedido_created: bool
    ocorrencia_created: bool


def seed_demo_environment(db: Session, demo: DemoEnvironmentSettings) -> DemoSeedResult:
    """Uma transacao: tres contas, um pedido e uma ocorrencia, sem sobrescritas.

    O vinculo e por Pedido.cliente_id / Pedido.responsavel_id, nao uma carteira
    permanente. Apenas o pedido DEMO e criado, no estado inicial PLANEAMENTO.
    Repositories reais persistem os dados; nenhum fluxo de transicao e executado.
    """
    if db.new or db.dirty or db.deleted:
        raise DemoSeedConflictError("Use uma sessao exclusiva para o seed DEMO.")
    try:
        if db.get_bind().dialect.name == "postgresql":
            # Serialize concurrent invocations without new tables/constraints.
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 604921360127})
        accounts = demo.accounts()
        users_repository = UserRepository(db)
        users: dict[PerfilEnum, User] = {}
        created_profiles: list[PerfilEnum] = []
        existing = db.scalars(select(User).where(
            func.lower(User.email).in_([account.DEMO_USER_EMAIL for account in accounts.values()]),
        )).all()
        # Check all pre-existing identities before creating any account.
        for perfil, account in accounts.items():
            matches = [user for user in existing if user.email.lower() == account.DEMO_USER_EMAIL]
            if len(matches) > 1:
                raise DemoSeedConflictError(f"E-mail ambiguo para DEMO {perfil.value}.")
            if matches:
                user = matches[0]
                if (user.email != account.DEMO_USER_EMAIL or user.perfil != perfil
                        or user.ativo is not True or not verify_password(
                            account.DEMO_USER_PASSWORD.get_secret_value(), user.senha_hash,
                        )):
                    raise DemoSeedConflictError(
                        f"Conta DEMO {perfil.value} existente incompativel; conta preservada."
                    )
                users[perfil] = user
        for perfil, account in accounts.items():
            if perfil not in users:
                users[perfil] = users_repository.create({
                    "nome": account.DEMO_USER_NAME,
                    "email": account.DEMO_USER_EMAIL,
                    "senha_hash": hash_password(account.DEMO_USER_PASSWORD.get_secret_value()),
                    "perfil": perfil,
                    "ativo": True,
                })
                created_profiles.append(perfil)

        admin, tecnico, cliente = (users[perfil] for perfil in (
            PerfilEnum.ADMIN, PerfilEnum.TECNICO, PerfilEnum.CLIENTE,
        ))
        pedidos = PedidoRepository(db)
        pedido = pedidos.get_by_codigo(DEMO_PEDIDO_CODIGO)
        pedido_created = pedido is None
        if pedido is None:
            pedido = pedidos.create({
                "codigo_identificador": DEMO_PEDIDO_CODIGO,
                "titulo": "[DEMO] Apresentacao Automatize",
                "descricao": "Pedido de demonstracao da persistencia e do vinculo por responsavel.",
                "status": StatusPedidoEnum.PLANEAMENTO,
                "cliente_id": cliente.id,
                "responsavel_id": tecnico.id,
            })
        elif pedido.cliente_id != cliente.id or pedido.responsavel_id != tecnico.id:
            raise DemoSeedConflictError("Codigo de pedido DEMO ja utilizado por outro vinculo.")

        ocorrencias = db.scalars(select(Ocorrencia).where(
            Ocorrencia.pedido_id == pedido.id,
            Ocorrencia.autor_id == cliente.id,
            Ocorrencia.tipo == TipoOcorrenciaEnum.ERRO,
            Ocorrencia.descricao == DEMO_OCORRENCIA_DESCRICAO,
        )).all()
        if len(ocorrencias) > 1:
            raise DemoSeedConflictError("Mais de uma ocorrencia DEMO encontrada; dados preservados.")
        ocorrencia_created = not ocorrencias
        if ocorrencias:
            ocorrencia = ocorrencias[0]
        else:
            if pedido.status == StatusPedidoEnum.CONCLUIDO:
                raise DemoSeedConflictError("Pedido DEMO concluido; nenhuma nova ocorrencia sera criada.")
            ocorrencia = BaseRepository(Ocorrencia, db).create({
                "pedido_id": pedido.id,
                "autor_id": cliente.id,
                "tipo": TipoOcorrenciaEnum.ERRO,
                "descricao": DEMO_OCORRENCIA_DESCRICAO,
            })
        if pedido_created or ocorrencia_created:
            BaseRepository(AuditoriaLog, db).create({
                "usuario_id": admin.id,
                "pedido_id": pedido.id,
                "acao": "SEED_DEMONSTRACAO",
                "detalhes": {"origem": "seed_demo_environment", "ocorrencia_id": str(ocorrencia.id)},
            })
        result = DemoSeedResult(
            user_ids={perfil: user.id for perfil, user in users.items()},
            created_profiles=tuple(created_profiles), pedido_id=pedido.id,
            ocorrencia_id=ocorrencia.id, pedido_created=pedido_created,
            ocorrencia_created=ocorrencia_created,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persistir os dados DEMO configurados.")
    args = parser.parse_args()
    engine = None
    try:
        demo = DemoEnvironmentSettings()
        if not args.apply:
            print("Configuracao DEMO valida. Sem escrita; use --apply para persistir.")
            return 0
        engine = create_database_engine(Settings())
        with create_session_factory(engine)() as db:
            result = seed_demo_environment(db, demo)
        print(f"Seed DEMO concluido; contas novas: {len(result.created_profiles)}; "
              f"pedido novo: {result.pedido_created}; ocorrencia nova: {result.ocorrencia_created}.")
        return 0
    except DemoSeedConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        # Never print exceptions from settings, SQLAlchemy, libpq or bcrypt:
        # their repr/tracebacks may contain credentials or database parameters.
        print("Seed DEMO nao concluido. Verifique configuracao, schema e conexao.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
