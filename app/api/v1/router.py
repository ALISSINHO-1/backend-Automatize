from fastapi import APIRouter

from app.api.v1.endpoints import auth, cadastro, contexto, comercial, chat, demandas, demandas_acoes, pedidos, usuarios

router = APIRouter()
api_router = router

endpoint_routers = (auth.router, cadastro.router, contexto.router, comercial.router, demandas.router, demandas_acoes.router, usuarios.router, chat.router)
for endpoint_router in endpoint_routers:
    router.include_router(endpoint_router)

router.include_router(pedidos.router, prefix="/pedidos", tags=["Pedidos"])
