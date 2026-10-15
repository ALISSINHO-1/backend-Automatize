# Automatize - Backend

Backend da plataforma **Automatize**, projeto acadêmico de Engenharia de Software. A aplicação FastAPI está preparada para execução local e disponibiliza uma verificação de saúde.

## Sobre o projeto

O Automatize busca centralizar solicitações, ajustes, informações e aprovações de pequenos empreendedores e organizações, com rastreabilidade durante o atendimento.

## Estado da implementação

### Disponível no repositório

- Modelos SQLAlchemy para usuários, pedidos, ocorrências, anexos, aceites formais e logs de auditoria.
- Migrações Alembic para o esquema do banco.
- Repositórios base e de pedidos com operações de persistência e consulta.
- Aplicação FastAPI, rota raiz e rota `GET /health`.
- Configuração de origens CORS por variável de ambiente.
- Routers internos de autenticação (`app/api/v1/endpoints/auth.py`) e demandas (`app/api/v1/endpoints/demandas.py`), agregados em `app/api/v1/router.py`.

Os routers estão preparados, mas ainda não declaram operações HTTP. Por isso, `/auth`, `/demandas` e `/pedidos` não aparecem como caminhos no Swagger enquanto estiverem vazios. O router de pedidos vindo da `main` foi preservado sob `/pedidos`, sem operações implementadas.

### Contratos previstos, ainda indisponíveis

- `POST /auth/login` será o contrato previsto para autenticação.
- `/demandas` será o caminho público previsto para futuras operações CRUD de demandas.
- Os caminhos públicos previstos não incluem o prefixo `/api/v1`, para manter compatibilidade com o contrato atual do frontend.
- A API poderá expor o recurso como “demandas” e reutilizar internamente a entidade `Pedido` e a tabela `pedidos`.
- `/demandas` é o nome público previsto para o contrato do frontend; `/pedidos` preserva o nome do router e da entidade existentes. Os dois caminhos não representam operações implementadas nesta etapa e não implicam renomear a entidade ou a tabela.
- Os identificadores persistidos são UUID e serão serializados como texto no JSON.

A estrutura dos routers está preparada nesta etapa, mas login e CRUD continuam pendentes e pertencem às próximas tarefas.

### Previsto para etapas futuras

- Implementação do login e dos endpoints CRUD de demandas, além das regras de negócio.
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
