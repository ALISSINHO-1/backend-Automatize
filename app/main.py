from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router

app = FastAPI(
    title="Automatize API",
    description="API para gestao de ordens de servico, integracao mobile e homologacao formal.",
    version="1.0.0"
)

# Permissao CORS para a aplicacao Flutter/Web se conectar sem bloqueios
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def raiz():
    return {
        "sistema": "Automatize API",
        "status": "Online",
        "docs": "/docs"
    }
