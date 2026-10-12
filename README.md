# Automatize - Backend

Backend da plataforma **Automatize**, projeto acadêmico de Engenharia de Software. Esta etapa prepara a API para execução local e disponibiliza uma verificação de saúde.

## Sobre o projeto

O Automatize busca centralizar solicitações, ajustes, informações e aprovações de pequenos empreendedores e organizações, com rastreabilidade durante o atendimento.

## Estado da implementação

### Disponível no repositório

- Modelos SQLAlchemy para usuários, pedidos, ocorrências, anexos, aceites formais e logs de auditoria.
- Migrações Alembic para o esquema do banco.
- Repositórios base e de pedidos com operações de persistência e consulta.
- Aplicação FastAPI, rota raiz, prefixo `/api/v1` e rota `GET /health`.
- Configuração de origens CORS por variável de ambiente.

Os modelos e repositórios não significam que existam endpoints HTTP de pedidos. Ainda não há rotas de domínio nem camada de serviços implementadas.

### Previsto para etapas futuras

- Endpoints CRUD e regras de negócio para pedidos e demais recursos.
- Autenticação e autorização.
- Regras de transição de status, cálculo de progresso e automações.
- Integrações de armazenamento e fluxos de aprovação.

## Pré-requisitos

- Python 3.10 ou superior.
- PostgreSQL para executar operações de persistência. A rota `/health` não acessa o banco.

## Execução local no Windows/PowerShell

Na raiz do repositório, execute:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Crie o `.env` apenas se ainda não existir, para preservar configurações locais:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Inicie a aplicação:

```powershell
python -m uvicorn app.main:app --reload
```

- Documentação interativa: <http://127.0.0.1:8000/docs>
- Verificação de saúde: <http://127.0.0.1:8000/health>

## CORS

Configure `CORS_ORIGINS` no `.env` como uma lista JSON de origens, por exemplo:

```dotenv
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
```

O padrão é uma lista vazia. Nesse caso, o middleware não autoriza acesso entre origens pelo navegador. Inclua cada origem permitida explicitamente.

## Testes

Execute a suíte com:

```powershell
python -m pytest -q
```
