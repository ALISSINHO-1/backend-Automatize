from fastapi import APIRouter

from app.api.v1.endpoints import auth, demandas

router = APIRouter()
endpoint_routers = (auth.router, demandas.router)

for endpoint_router in endpoint_routers:
    router.include_router(endpoint_router)
