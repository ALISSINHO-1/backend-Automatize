"""Contextos comerciais autorizados calculados no servidor, nao no Flutter."""
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_account_user
from app.core.database import get_db
from app.domain.models.user import User
from app.domain.models.organizacao import Organizacao
from app.domain.models.organizacao_usuario import OrganizacaoUsuario
from app.domain.models.contratacao import Contratacao

router = APIRouter(prefix="/auth", tags=["Ambientes"])

class AmbienteResponse(BaseModel):
    tipo: str
    contratacao_id: UUID
    organizacao_id: UUID | None = None
    papel: str
    nome: str

class ContextoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    perfil: str
    situacao_cadastro: str
    ambientes: list[AmbienteResponse]

@router.get("/contexto", response_model=ContextoResponse)
def meu_contexto(
    usuario: User = Depends(get_account_user),
    db: Session = Depends(get_db),
) -> ContextoResponse:
    situacao = usuario.situacao_cadastro or "ATIVO"
    ambientes: list[AmbienteResponse] = []
    if situacao == "ATIVO":
        # Contratos DEV sao pessoais e visiveis apenas ao titular.
        contratos_dev = db.scalars(
            select(Contratacao).where(
                Contratacao.tipo == "DEV",
                Contratacao.situacao == "ATIVA",
                Contratacao.usuario_cliente_id == usuario.id,
            )
        ).all()
        for contrato in contratos_dev:
            ambientes.append(AmbienteResponse(
                tipo="DEV", contratacao_id=contrato.id,
                papel="CLIENTE", nome="Meus projetos DEV",
            ))

        # SaaS exige contrato da empresa, vinculo ativo e empresa ativa.
        vinculos = db.execute(
            select(Organizacao, OrganizacaoUsuario, Contratacao)
            .join(OrganizacaoUsuario, OrganizacaoUsuario.organizacao_id == Organizacao.id)
            .join(Contratacao, Contratacao.organizacao_id == Organizacao.id)
            .where(
                OrganizacaoUsuario.usuario_id == usuario.id,
                OrganizacaoUsuario.ativo.is_(True),
                Organizacao.ativa.is_(True),
                Contratacao.tipo == "SAAS",
                Contratacao.situacao == "ATIVA",
            )
        ).all()
        for org, vinculo, contrato in vinculos:
            ambientes.append(AmbienteResponse(
                tipo="SAAS", contratacao_id=contrato.id,
                organizacao_id=org.id, papel=vinculo.papel, nome=org.nome,
            ))

    return ContextoResponse(
        id=usuario.id, perfil=usuario.perfil.value,
        situacao_cadastro=situacao, ambientes=ambientes,
    )
