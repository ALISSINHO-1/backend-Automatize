from fastapi import APIRouter
from app.api.v1.endpoints import pedidos

api_router = APIRouter()
api_router.include_router(pedidos.router, prefix="/pedidos", tags=["Pedidos"])
