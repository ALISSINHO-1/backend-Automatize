# Automatize - Backend

Backend FastAPI do projeto acadêmico Automatize. A API expõe documentação OpenAPI, login com JSON, consultas autenticadas de demandas e uma rota de saúde.

## Estado da implementação

- Modelos SQLAlchemy, repositórios base, de usuários e de pedidos, além de revisões Alembic existentes.
- Configurações centralizadas em `app/core/config.py`; engine e fábrica de sessões são preparadas no startup.
- `POST /auth/login` autentica usuários persistidos e emite JWT HS256 com `sub`, `iat` e `exp`.
- `GET /demandas` e `GET /demandas/{id}` exigem Bearer e aplicam a política de acesso descrita abaixo.
- `GET /health` retorna `{"status":"ok"}` sem consultar banco ou serviços externos.
- A integração real com PostgreSQL ainda não foi validada. A inicialização prepara a engine, mas não confirma conectividade ou compatibilidade do esquema.

## Requisitos e instalação

- Python 3.10 ou superior.
- PostgreSQL para operações reais de persistência.

No Windows/PowerShell, na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edite o `.env` local e substitua os valores de exemplo. O comando de cópia preserva um `.env` que já exista.

## Configuração

| Variável | Formato | Uso |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://USUARIO:SENHA@HOST:5432/BANCO` | Obrigatória para iniciar a API. |
| `JWT_SECRET_KEY` | Segredo aleatório com pelo menos 32 caracteres | Obrigatório para iniciar a API; não use o placeholder do exemplo. |
| `JWT_ALGORITHM` | `HS256` | Único algoritmo habilitado. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Inteiro maior que zero | Prazo dos tokens; padrão `30`. |
| `STORAGE_BUCKET_NAME` | Nome do bucket | Padrão `evidencias-anexos`. |
| `CORS_ORIGINS` | Lista JSON de origens | Padrão `[]`; não use `*` com credenciais habilitadas. |

Gere uma chave localmente com:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o resultado para `JWT_SECRET_KEY` no `.env`. Não compartilhe a chave nem a inclua no controle de versão.

## Login e uso do Bearer

`POST /auth/login` recebe JSON; o login não usa formulário OAuth2:

```json
{
  "email": "cliente@example.com",
  "senha": "senha-do-usuario"
}
```

Resposta `200`:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer"
}
```

O token representa o UUID persistido do usuário em `sub`, além de `iat` e `exp`. As consultas validam assinatura HS256 usando a chave da instância da aplicação e carregam o usuário ativo novamente do banco. Perfil e escopo vêm desse usuário persistido.

No Swagger em `/docs`, execute `POST /auth/login`, copie o valor de `access_token`, clique em **Authorize** e cole o token no campo Bearer. Depois execute uma consulta protegida. Clientes HTTP também devem enviar `Authorization: Bearer <token>`.

Usuário inexistente, senha incorreta, hash inválido ou conta inativa no login retornam `401` genérico e `WWW-Authenticate: Bearer`. Falhas de persistência não são convertidas em `401`. Corpo ausente ou campos inválidos retornam `422` sem incluir valores rejeitados.

Bcrypt considera no máximo os primeiros 72 bytes da senha. O login e a geração de hash rejeitam entradas acima de 72 bytes UTF-8; não truncam, normalizam nem removem espaços. O limite é em bytes, não em caracteres. `requirements.txt` limita bcrypt a versões anteriores à 4.1 para compatibilidade com Passlib 1.7.4.

## Consultas de demandas

### `GET /demandas`

Retorna uma lista JSON, que pode ser vazia quando a consulta não encontrar registros. A ordenação é crescente por `created_at` e `id`.

Parâmetros de paginação:

- `offset`: inteiro maior ou igual a zero; padrão `0`.
- `limit`: inteiro entre `1` e `100`; padrão `100`.

Exemplo fictício: `GET /demandas?offset=0&limit=25`.

### `GET /demandas/{id}`

Consulta uma demanda pelo UUID. Um registro inexistente ou fora do escopo do usuário retorna `404`.

Exemplo fictício: `GET /demandas/ca57c5bc-0efa-4202-9c3e-7b46c560bbef`.

### Política de acesso desta entrega

- `ADMIN`: consulta todas as demandas.
- `CLIENTE`: consulta somente registros cujo `cliente_id` seja o UUID do usuário autenticado.
- `TECNICO`: consulta somente registros cujo `responsavel_id` seja o UUID do usuário autenticado.
- Perfil desconhecido: recebe `403`.

A listagem filtra no repositório antes de aplicar a paginação. A consulta de detalhe usa o mesmo escopo e responde `404` para ocultar registros alheios. Esta é a política adotada nesta implementação; ela não é uma regra comprovada pelo DER.

### Campos de resposta

A resposta de cada demanda contém somente:

| Campo | Representação |
| --- | --- |
| `id`, `cliente_id`, `responsavel_id` | UUID em string; `responsavel_id` pode ser `null`. |
| `codigo_identificador`, `titulo` | String. |
| `descricao` | String ou `null`, conforme o modelo. |
| `status` | Enum persistido (`PLANEAMENTO`, `EXECUCAO`, `HOMOLOGACAO`, `CONCLUIDO`). |
| `percentual_progresso` | Decimal como string, por exemplo `"37.50"`, para preservar precisão; pode ser `null`. |
| `created_at`, `updated_at` | Data/hora ISO 8601 ou `null`, conforme a nulabilidade do modelo. |

Exemplo fictício de item:

```json
{
  "id": "ca57c5bc-0efa-4202-9c3e-7b46c560bbef",
  "codigo_identificador": "DEM-0001",
  "titulo": "Atualizar painel",
  "descricao": null,
  "status": "PLANEAMENTO",
  "percentual_progresso": "0.00",
  "cliente_id": "b32e49ec-f8dd-4a8f-9ae9-dc3f90b4a4b1",
  "responsavel_id": null,
  "created_at": "2026-05-06T07:08:00Z",
  "updated_at": "2026-05-06T07:08:00Z"
}
```

As consultas podem responder `200` (resultado/lista), `401` (Bearer ausente ou inválido), `403` (perfil desconhecido), `404` (detalhe inexistente ou fora do escopo) e `422` (UUID ou paginação inválidos), conforme a rota. `/auth/login` e `/health` continuam públicos.

A duplicação entre `app/domain/enums.py` e `app/domain/models/enums.py` permanece como pendência técnica. As consultas usam os enums persistidos em `app/domain/models/enums.py`, preservando `PLANEAMENTO`; esta entrega não renomeia nem unifica enums.

## Executar

```powershell
python -m uvicorn app.main:app --reload
```

- OpenAPI: <http://127.0.0.1:8000/docs>
- Saúde: <http://127.0.0.1:8000/health>

No startup, a aplicação valida configuração e prepara a engine sem abrir conexão. Isso não valida a conectividade com PostgreSQL nem o esquema do banco. Para uma verificação manual de conexão com um banco escolhido, configure `.env` e execute `python test_db.py` (`SELECT 1`). Nenhuma validação de PostgreSQL real foi feita nesta entrega.

## Testes

Os testes unitários usam Settings explícitas e simulam persistência, sem depender do `.env` local ou de uma conexão real:

```powershell
python -m pytest -q
```

O frontend precisará tratar UUID como string, enviar o Bearer e usar uma URL base configurável para a API.
