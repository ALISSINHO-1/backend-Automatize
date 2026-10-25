"""
Configurações e fixtures compartilhadas
da suíte de testes do Automatize.
"""
import os

from dotenv import load_dotenv  # type: ignore

# Os testes de regra de negocio nao acessam o banco, mas importar os models
# carrega app.core.database, que exige DATABASE_URL. Sem .env, usa SQLite em
# memoria para que a suite rode sem PostgreSQL nem driver instalados.
load_dotenv()
os.environ.setdefault("DATABASE_URL", "sqlite://")
