from fastapi import APIRouter

from app.api.v1.endpoints import auth, demandas, demandas_acoes, pedidos

router = APIRouter()
api_router = router

endpoint_routers = (auth.router, demandas.router, demandas_acoes.router)
for endpoint_router in endpoint_routers:
    router.include_router(endpoint_router)

router.include_router(pedidos.router, prefix="/pedidos", tags=["Pedidos"])
