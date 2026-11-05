from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.aceite_formal import AceiteFormal
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.domain.models.historico_status_pedido import HistoricoStatusPedido
from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository
from app.repositories.user_repository import UserRepository
from app.services.pedido_service import PedidoNaoEncontradoError


class AprovacaoService:
    """Persiste aceite, conclusão, histórico e auditoria na mesma transação."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def registrar_aceite(
        self,
        *,
        pedido_id: UUID,
        cliente_id: UUID,
        versao_entregavel: str,
        declaracao_aceite: str,
        status_esperado: StatusPedidoEnum | None = None,
    ) -> AceiteFormal:
        """The caller must supply the authenticated user's ID, never a body ID."""
        if not versao_entregavel.strip() or len(versao_entregavel) > 50:
            raise ValueError("Informe uma versão do entregável de até 50 caracteres.")
        if not declaracao_aceite.strip():
            raise ValueError("A declaração de aceite é obrigatória.")

        try:
            # Serialize approvals of the same order without changing the schema.
            pedido = self.db.scalar(
                select(Pedido).where(Pedido.id == pedido_id).with_for_update()
                .execution_options(populate_existing=True)
            )
            if pedido is None:
                raise PedidoNaoEncontradoError("Pedido não encontrado.")
            cliente = UserRepository(self.db).get_by_id(cliente_id)
            if (
                cliente is None or cliente.ativo is not True
                or cliente.perfil != PerfilEnum.CLIENTE
                or pedido.cliente_id != cliente_id
            ):
                raise PermissionError("Somente o cliente do pedido pode registrar aceite.")
            if status_esperado is not None and pedido.status != status_esperado:
                raise ValueError("O status informado diverge do pedido persistido.")
            if pedido.status != StatusPedidoEnum.HOMOLOGACAO:
                raise ValueError("O pedido deve estar em HOMOLOGACAO para receber aceite.")

            aceite_id = uuid4()
            timestamp = datetime.now(timezone.utc)
            dados_validacao = {
                "id": str(aceite_id), "pedido_id": str(pedido_id),
                "cliente_id": str(cliente_id), "data_hora_aceite": timestamp.isoformat(),
                "versao_entregavel": versao_entregavel,
                "declaracao_aceite": declaracao_aceite,
            }
            digest = sha256(json.dumps(
                dados_validacao, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            aceite = BaseRepository(AceiteFormal, self.db).create({
                "id": aceite_id, "pedido_id": pedido_id, "cliente_id": cliente_id,
                "data_hora_aceite": timestamp,
                "versao_entregavel": versao_entregavel,
                "declaracao_aceite": declaracao_aceite, "hash_validacao": digest,
            })
            BaseRepository(HistoricoStatusPedido, self.db).create({
                "pedido_id": pedido_id, "usuario_id": cliente_id,
                "status_anterior": pedido.status,
                "status_novo": StatusPedidoEnum.CONCLUIDO,
            })
            BaseRepository(AuditoriaLog, self.db).create({
                "usuario_id": cliente_id, "pedido_id": pedido_id,
                "acao": "ACEITE_FORMAL",
                "detalhes": {"aceite_id": str(aceite_id), "hash_validacao": digest},
            })
            pedido.status = StatusPedidoEnum.CONCLUIDO
            pedido.percentual_progresso = Decimal("100.00")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(aceite)
        return aceite

    @classmethod
    def homologar_entrega(
        cls,
        pedido_id: UUID,
        status_atual: StatusPedidoEnum,
        cliente_id: str,
        *,
        db: Session | None = None,
        versao_entregavel: str = "",
        declaracao_aceite: str = "",
    ) -> dict[str, Any]:
        """Keep the HML entry point; persistence requires explicit session/evidence."""
        if db is None:
            raise ValueError("Uma sessão é obrigatória para persistir o aceite formal.")
        aceite = cls(db).registrar_aceite(
            pedido_id=pedido_id, cliente_id=UUID(cliente_id),
            versao_entregavel=versao_entregavel, declaracao_aceite=declaracao_aceite,
            status_esperado=status_atual,
        )
        return {
            "pedido_id": pedido_id, "status_final": StatusPedidoEnum.CONCLUIDO.value,
            "aprovado_por": cliente_id, "data_aceite": aceite.data_hora_aceite,
            "percentual_progresso": 100.0, "mensagem": "Aceite formal registrado.",
        }
