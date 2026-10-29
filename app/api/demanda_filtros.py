from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Query

from app.domain.models.enums import StatusPedidoEnum


class DemandaFiltros:
    def __init__(
        self,
        busca: str | None = Query(None, min_length=1, max_length=200),
        estado: StatusPedidoEnum | None = None,
        cliente_id: UUID | None = None,
        responsavel_id: UUID | None = None,
        inicio: datetime | None = Query(
            None, description="Criação a partir desta data ISO 8601, com fuso horário."
        ),
        fim: datetime | None = Query(
            None, description="Criação até esta data ISO 8601, com fuso horário."
        ),
    ):
        if any(data is not None and data.tzinfo is None for data in (inicio, fim)):
            raise HTTPException(
                422, "Informe o fuso horário nas datas de início e fim."
            )
        if inicio is not None and fim is not None and inicio > fim:
            raise HTTPException(422, "Início deve ser anterior ou igual ao fim.")
        self.values = {
            k: v
            for k, v in dict(
                busca=busca,
                estado=estado,
                cliente_id=cliente_id,
                responsavel_id=responsavel_id,
                inicio=inicio,
                fim=fim,
            ).items()
            if v is not None
        }
