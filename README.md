# Automatize - Backend

Backend FastAPI do projeto acadêmico Automatize. A API expõe documentação OpenAPI, login com JSON, consultas autenticadas de demandas e uma rota de saúde.

## Estado da implementação

- Modelos SQLAlchemy, repositórios base, de usuários e de pedidos, além de revisões Alembic existentes.
- Configurações centralizadas em `app/core/config.py`; engine e fábrica de sessões são preparadas no startup.
- `POST /auth/login` autentica usuários persistidos e emite JWT HS256 com `sub`, `iat` e `exp`.
- `GET /demandas` e `GET /demandas/{id}` exigem Bearer e aplicam a política de acesso descrita abaixo.
- `GET /health` retorna `{"status":"ok"}` sem consultar banco ou serviços externos.
- Em 23/10/2026, `alembic current` e `alembic check` confirmaram o banco em `fd3fe1dcfeab (head)` e sem diferenças de estrutura. A inspeção somente leitura confirmou PKs, FKs, constraints e índices declarados nas sete tabelas. A inicialização da API continua sem abrir conexão.

## Requisitos e instalação

- Python 3.14 ou superior (validação realizada com Python 3.14.7).
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
| `SUPABASE_URL` | URL do projeto Supabase | Necessária apenas ao utilizar Storage. |
| `SUPABASE_KEY` | Chave autorizada para o bucket | Necessária apenas ao utilizar Storage; nunca expor no frontend. |
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

Bcrypt considera no máximo os primeiros 72 bytes da senha. O login e a geração de hash rejeitam entradas acima de 72 bytes UTF-8; não truncam, normalizam nem removem espaços. O limite é em bytes, não em caracteres. `requirements.txt` fixa Passlib 1.7.4 e bcrypt 4.3.0, combinação validada com Python 3.14. O probe interno do Passlib é incompatível com bcrypt 5.0. A versão 4.3.0 ainda pode registrar o aviso de leitura de `bcrypt.__about__`; os testes de hash e login passam sem adaptar ou truncar senhas.

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

No startup, a aplicação valida configuração e prepara a engine sem abrir conexão. Para uma verificação manual de conexão com um banco escolhido, configure `.env` e execute `python test_db.py` (`SELECT 1`). As verificações Alembic e de catálogo descritas acima não executaram alterações no banco.

## Testes

Os testes unitários usam Settings explícitas e simulam persistência, sem depender do `.env` local ou de uma conexão real:

```powershell
python -m pytest -q
```

O frontend precisará tratar UUID como string, enviar o Bearer e usar uma URL base configurável para a API.

## Usuário de demonstração

O seed é um comando manual de desenvolvimento. Ele não roda no startup nem em migrations e não foi executado contra o banco durante a auditoria.

Configure `DEMO_USER_NAME`, `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` no ambiente ou no `.env` local, apontando `DATABASE_URL` para o banco de desenvolvimento escolhido. Não inclua credenciais reais em arquivos versionados nem em argumentos de linha de comando. Depois execute:

```powershell
python -m scripts.seed_demo_user
```

O comando usa `app.core.security.hash_password`, o mesmo mecanismo do login, cria somente um `CLIENTE` ativo e persiste apenas `senha_hash`. A senha deve conter de 1 a 72 bytes UTF-8. Se o e-mail já existir, preserva a conta, o perfil e a senha existentes. Também trata duas execuções concorrentes pela restrição UNIQUE de e-mail. Não reseta senha nem reativa uma conta existente.

## Aceite formal e anexos

`AprovacaoService(db).registrar_aceite(...)` exige UUIDs do pedido e do cliente autenticado, versão do entregável e declaração de aceite. Valida cliente ativo e proprietário, bloqueia o pedido com `FOR UPDATE` e exige `HOMOLOGACAO`. Persiste aceite, hash SHA-256 dos dados de evidência, histórico e auditoria, concluindo o pedido com 100% em um único commit. O hash não é uma assinatura digital. O método HML `homologar_entrega` foi preservado como adaptador e agora requer sessão e evidências explícitas.

Ainda não há rota REST de aprovação ou de upload. Na futura rota, o cliente deve vir de `get_current_user`, e não ser confiado ao corpo da requisição. Os schemas HML de aprovação/pedido ainda contêm IDs inteiros e devem ser alinhados a UUID na integração das rotas; os contratos atuais de login e consulta de demandas foram preservados.

O cliente Supabase é criado sob demanda na infraestrutura. `app/core/storage.py` preserva os imports antigos sem criar cliente ao importar o módulo. `AnexoService` controla upload, metadados e compensação quando a persistência falha; falha de refresh após commit não remove o arquivo já referenciado pelo banco. Os testes atuais usam Storage simulado e não realizam upload real.

## SCRUM-39

A listagem atual usa `GET /demandas` com Bearer, escopo por usuário e paginação. Para atualização periódica da interface, a abordagem inicial é polling no frontend, com intervalo alinhado à necessidade da apresentação, atualização ao voltar o foco e pausa em abas ocultas. Preserve filtros e paginação e trate expiração do token. Não foi implementado polling ou scheduler. SSE pode ser avaliado posteriormente caso seja necessário receber mudanças imediatamente.

O relatório de auditoria e o estado das tarefas estão em `docs/backend-audit.md`.
