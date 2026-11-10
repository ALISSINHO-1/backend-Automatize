from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.domain.models.chat_mensagem import ChatMensagem
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.domain.regras.autorizacao import is_admin, is_cliente_dono, is_responsavel

Canal = Literal["cliente", "interno"]
router = APIRouter(prefix="/demandas/{pedido_id}/chat", tags=["Chat"])


class NovaMensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

    @field_validator("texto")
    @classmethod
    def recusar_caractere_nulo(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("A mensagem não pode conter caracteres nulos.")
        return value


class MensagemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    autor_id: UUID
    autor_nome: str
    texto: str
    criado_em: datetime


class HistoricoResponse(BaseModel):
    mensagens: list[MensagemResponse]
    antes_de: UUID | None


def _validar_conversa(db: Session, pedido_id: UUID, canal: Canal, usuario: User) -> None:
    # Mantém a atribuição estável até terminar a leitura ou gravar a mensagem.
    pedido = db.scalar(
        select(Pedido).where(Pedido.id == pedido_id).with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if pedido is None:
        raise HTTPException(404, "Conversa não encontrada.")
    permitido = is_responsavel(usuario, pedido)
    outro_participante = is_cliente_dono(usuario, pedido) if canal == "cliente" else is_admin(usuario)
    if not (permitido or outro_participante):
        raise HTTPException(404, "Conversa não encontrada.")
    if pedido.responsavel_id is None:
        raise HTTPException(409, "A demanda ainda não tem um técnico responsável.")


@router.get("/{canal}", response_model=HistoricoResponse)
def listar_mensagens(
    pedido_id: UUID,
    canal: Canal,
    antes_de: UUID | None = None,
    limite: int = Query(50, ge=1, le=100),
    usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validar_conversa(db, pedido_id, canal, usuario)
    escopo = (ChatMensagem.pedido_id == pedido_id, ChatMensagem.canal == canal)
    consulta = (
        select(ChatMensagem, User.nome)
        .join(User, User.id == ChatMensagem.autor_id)
        .where(*escopo)
    )
    if antes_de is not None:
        cursor = db.scalar(select(ChatMensagem).where(*escopo, ChatMensagem.id == antes_de))
        if cursor is None:
            raise HTTPException(404, "Mensagem não encontrada nesta conversa.")
        consulta = consulta.where(
            tuple_(ChatMensagem.criado_em, ChatMensagem.id) < (cursor.criado_em, cursor.id)
        )
    linhas = db.execute(
        consulta.order_by(ChatMensagem.criado_em.desc(), ChatMensagem.id.desc()).limit(limite + 1)
    ).all()
    return HistoricoResponse(
        mensagens=[_resposta(mensagem, nome) for mensagem, nome in linhas[:limite]],
        antes_de=linhas[limite - 1][0].id if len(linhas) > limite else None,
    )


def _resposta(mensagem: ChatMensagem, nome: str) -> MensagemResponse:
    return MensagemResponse(
        id=mensagem.id,
        autor_id=mensagem.autor_id,
        autor_nome=nome,
        texto=mensagem.texto,
        criado_em=mensagem.criado_em,
    )


@router.post("/{canal}", response_model=MensagemResponse, status_code=201)
def enviar_mensagem(
    pedido_id: UUID,
    canal: Canal,
    dados: NovaMensagem,
    usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validar_conversa(db, pedido_id, canal, usuario)
    mensagem = ChatMensagem(
        id=uuid4(), pedido_id=pedido_id, autor_id=usuario.id, canal=canal, texto=dados.texto
    )
    db.add(mensagem)
    db.flush()
    resposta = _resposta(mensagem, usuario.nome)
    db.commit()
    return resposta
