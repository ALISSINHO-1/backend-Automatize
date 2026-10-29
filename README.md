# Automatize - Backend

Backend FastAPI do projeto acadêmico Automatize. A API expõe documentação OpenAPI, login com JSON, consultas autenticadas de demandas e uma rota de saúde.

## Estado da implementação

- Modelos SQLAlchemy, repositórios base, de usuários e de pedidos, além de revisões Alembic existentes.
- Configurações centralizadas em `app/core/config.py`; engine e fábrica de sessões são preparadas no startup.
- `POST /auth/login` autentica usuários persistidos e emite JWT HS256 com `sub`, `iat` e `exp`.
- `GET /demandas` e `GET /demandas/{id}` exigem Bearer e aplicam a política de acesso descrita abaixo.
- Rotas de escrita de demandas (cadastro, ciclo de vida, etapas, aceite, rejeição, evidências e histórico) usam o usuário do token; veja "Regras de negócio e rotas de escrita".
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

Os testes de integração (`tests/integration`) rodam contra um PostgreSQL real: aplicam as migrations, inclusive as triggers, e cada teste é desfeito ao final. Eles são ignorados quando `TEST_DATABASE_URL` não está definida. Use um banco descartável cujo nome contenha `test`, nunca o banco compartilhado:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:senha@localhost:5432/automatize_test"
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

As rotas de aprovação e de upload estão descritas em "Regras de negócio e rotas de escrita": o cliente vem de `get_current_user`, nunca do corpo da requisição. O schema de aprovação foi alinhado a UUID; os contratos atuais de login e consulta de demandas foram preservados.

## Regras de negócio e rotas de escrita

`DemandService(db)` (`app/services/demand_service.py`) aplica as regras do ciclo de vida sobre o `Pedido` persistido. Toda operação recebe o usuário autenticado, que define a permissão e é gravado como autor em `auditoria_logs` e `historico_status_pedidos`. As regras puras (máquina de estados, progresso e validação de arquivos) ficam em `app/domain/regras/` e também são usadas pelo `PedidoService`.

| Rota (Bearer obrigatório) | Quem pode | Regra |
| --- | --- | --- |
| `POST /demandas` | CLIENTE (para si) ou ADMIN (informando `cliente_id`) | Nasce em `PLANEAMENTO` com 15%. |
| `PATCH /demandas/{id}` | Cliente da demanda ou ADMIN | Título ≥ 3 e descrição ≥ 5 caracteres. |
| `DELETE /demandas/{id}` | ADMIN | Demandas concluídas não podem ser excluídas. |
| `PUT /demandas/{id}/responsavel` | ADMIN | O responsável deve ser um TECNICO ativo. |
| `POST /demandas/{id}/status` | Técnico responsável ou ADMIN | `PLANEAMENTO → EXECUCAO → HOMOLOGACAO`; etapas pendentes bloqueiam a homologação. `CONCLUIDO` só pelo aceite. |
| `GET/POST /demandas/{id}/etapas`, `POST .../etapas/{etapa_id}/conclusao` | Técnico responsável ou ADMIN (leitura: quem vê a demanda) | Etapas em `PLANEAMENTO`/`EXECUCAO`; conclusão só em `EXECUCAO`. Em `EXECUCAO`, progresso = 15 + 70 × concluídas/total. |
| `POST /demandas/{id}/aceite` | Somente o cliente da demanda | Exige `HOMOLOGACAO`; grava aceite com hash SHA-256 e conclui com 100%. |
| `POST /demandas/{id}/rejeicao` | Somente o cliente da demanda | Motivo ≥ 10 caracteres; volta para `EXECUCAO` e registra ocorrência `REGRESSO_ESTADO`. |
| `POST /demandas/{id}/evidencias` | Cliente, técnico responsável ou ADMIN | Multipart `arquivo`; aceita `pdf`, `png`, `jpg`, `jpeg` e `docx` até 10 MB. |
| `GET /demandas/{id}/historico` | Quem vê a demanda | Auditoria somente leitura, com o autor de cada ação. |

Demandas fora do escopo do usuário respondem 404; falta de permissão responde 403; violação de estado ou de imutabilidade responde 409; dados inválidos respondem 422. Corpos com campos desconhecidos (por exemplo um `cliente_id` no aceite) são recusados com 422.

**Validação de evidências.** O conteúdo real precisa ter a assinatura do formato declarado (um executável renomeado para `.png` é recusado). PDFs com JavaScript, ações ou arquivos embutidos e DOCX com macros são recusados, e o DOCX tem limite de conteúdo descompactado. O `content-type` enviado ao Storage é o detectado, não o informado pelo cliente. O `.doc` legado deixou de ser aceito por não permitir verificar macros com segurança.

**Imutabilidade do aceite (SCRUM-72).** Além das checagens do service, o modelo `AceiteFormal` recusa UPDATE/DELETE no ORM e a migration `3c9e7a1b5d20` cria no PostgreSQL: um aceite por pedido (`UNIQUE`), trigger que impede alterar ou excluir aceites, trigger que impede alterar ou excluir pedidos `CONCLUIDO` e que só permite chegar a `CONCLUIDO` quando existe aceite. Essas regras valem para qualquer cliente do banco, inclusive `PedidoService.atualizar`.

O cliente Supabase é criado sob demanda na infraestrutura. `app/core/storage.py` preserva os imports antigos sem criar cliente ao importar o módulo. `AnexoService` controla upload, metadados e compensação quando a persistência falha; falha de refresh após commit não remove o arquivo já referenciado pelo banco. Os testes atuais usam Storage simulado e não realizam upload real.

## SCRUM-39

A listagem atual usa `GET /demandas` com Bearer, escopo por usuário e paginação. Para atualização periódica da interface, a abordagem inicial é polling no frontend, com intervalo alinhado à necessidade da apresentação, atualização ao voltar o foco e pausa em abas ocultas. Preserve filtros e paginação e trate expiração do token. Não foi implementado polling ou scheduler. SSE pode ser avaliado posteriormente caso seja necessário receber mudanças imediatamente.

O relatório de auditoria e o estado das tarefas estão em `docs/backend-audit.md`.


## API e documentação — complemento de 29/10/2026

Acesse `/docs` após iniciar `uvicorn app.main:app --reload`. O Swagger possui grupos
por domínio, busca, operações recolhidas e exemplos. Faça login com JSON `email`/`senha`
e informe somente `access_token` em **Authorize**. A autorização não é persistida no navegador.

- `PUT /demandas/{id}` atualiza título e descrição; `PATCH` permanece compatível.
- `/demandas/{id}/ocorrencias`: POST e GET paginado; `/{ocorrencia_id}`: GET e PUT.
  O token define o autor. Apenas autor ou ADMIN edita a descrição. Registros de rejeição
  e demandas concluídas são imutáveis; tipo, autor e vínculo não são editáveis.
- `GET /demandas/{id}/anexos`: metadados paginados sem caminho do bucket.
  `GET /demandas/{id}/anexos/{anexo_id}/acesso`: após autorizar, redireciona a link
  assinado com validade de 60 segundos. Esse link é uma credencial temporária:
  não o grave em logs nem o compartilhe. O bucket deve continuar privado.
- `GET /demandas`: aceita `busca`, `estado`, `cliente_id`, `responsavel_id`, `inicio`,
  `fim`, `offset`, `limit` e `incluir_totais=true`. Datas precisam de fuso ISO 8601.
  A resposta continua sendo uma lista; os headers `X-Total-Count` e `X-Counts-By-Status`
  apresentam totais de todos os resultados filtrados autorizados, antes da paginação.
  Os filtros adicionais nunca substituem o escopo de acesso do usuário.

### Verificação reproduzível

```bash
python -m pip install -r requirements.txt
python -m pytest -ra
# PostgreSQL descartável: nome do banco contendo "test"; nunca usar produção.
export TEST_DATABASE_URL='postgresql+psycopg2://usuario:senha@localhost/automatize_test'
python -m pytest tests/integration -ra
```

O workflow `.github/workflows/api.yml` executa migrations do zero e a suíte em
PostgreSQL 17 descartável, com credenciais exclusivas de teste e relatório JUnit.
Os testes `test_api_completion_sql.py` cobrem HTTP com SQL real em SQLite; não
substituem a validação de locks, triggers e migrations no job PostgreSQL.

### Separação de responsabilidades

Rotas validam o contrato e traduzem exceções; services autorizam, aplicam regras,
controlam transações e auditoria; repositories executam as consultas SQL.
A revisão completa SCRUM-86 ainda deve tratar SQL legado existente no `DemandService`
(histórico e bloqueio de pedido). Este complemento usa repositories nas novas consultas.
Não há migration de estado de ocorrência: o modelo atual possui tipo e descrição;
qualquer ciclo adicional de resolução deve ser alinhado com Luís e Henrique.
