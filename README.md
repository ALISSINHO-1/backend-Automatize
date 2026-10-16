# Automatize - Backend

Backend FastAPI do projeto acadêmico Automatize. A aplicação disponibiliza documentação OpenAPI e uma rota de saúde sem dependência de serviços externos.

## Estado da implementação

- Modelos SQLAlchemy, repositórios base e de pedidos e revisões Alembic existentes.
- Configurações centralizadas em `app/core/config.py`.
- Engine PostgreSQL e fábrica de sessões configuradas no startup, sem abrir conexão nessa etapa.
- `POST /auth/login` autentica usuários persistidos e emite JWT HS256.
- Routers de demandas preparados, ainda sem operações HTTP.
- `GET /health` retorna `{"status":"ok"}` e não consulta banco ou serviços externos.

Validação de Bearer Token nas demais rotas, CRUD e regras de negócio permanecem para etapas futuras.

## Requisitos e instalação

- Python 3.10 ou superior.
- PostgreSQL acessível para operações de persistência.

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
| `DATABASE_URL` | `postgresql+psycopg2://USUARIO:SENHA@HOST:5432/BANCO` | Obrigatória para iniciar a API. Deve apontar para PostgreSQL usando psycopg2. |
| `JWT_SECRET_KEY` | Segredo aleatório com pelo menos 32 caracteres | Obrigatório para iniciar a API. O placeholder do exemplo é inválido. |
| `JWT_ALGORITHM` | `HS256` | Único algoritmo habilitado nesta etapa. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Inteiro maior que zero | Prazo configurado para tokens futuros. Padrão: `30`. |
| `STORAGE_BUCKET_NAME` | Nome do bucket | Padrão: `evidencias-anexos`. |
| `CORS_ORIGINS` | Lista JSON de origens | Padrão: `[]`; não use `*` com credenciais habilitadas. |

## Login

`POST /auth/login` recebe JSON e retorna um token de acesso:

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

Usuário inexistente, senha incorreta, hash armazenado inválido ou conta inativa retornam a mesma resposta `401`: `{"detail":"Credenciais inválidas."}` e `WWW-Authenticate: Bearer`. Falhas de persistência retornam erro genérico `500`, sem detalhes internos. Corpo ausente, malformado ou com campos inválidos retorna `422`; a resposta não inclui os valores rejeitados.

O login exige um usuário previamente persistido na tabela `users`, com senha armazenada como hash bcrypt compatível. A verificação usa Passlib com bcrypt; não aceita senha em texto puro. Configure `JWT_SECRET_KEY`, `JWT_ALGORITHM=HS256` e `ACCESS_TOKEN_EXPIRE_MINUTES` conforme a tabela acima. O JWT contém o UUID do usuário em `sub`, e os timestamps UTC `iat` e `exp`; não inclui dados de senha ou o segredo.

`requirements.txt` limita bcrypt a versões anteriores à 4.1 enquanto o projeto usa Passlib 1.7.4. Essa combinação evita a incompatibilidade conhecida em que Passlib tenta ler `bcrypt.__about__.__version__`, atributo removido no bcrypt 4.1; com versões mais novas o hashing pode continuar funcionando, mas Passlib registra um traceback de diagnóstico a cada inicialização do backend. A versão instalada neste ambiente é bcrypt 4.0.1. O projeto e os testes usam Passlib/bcrypt apenas em `app/core/security.py` e nos testes de autenticação; não há uso em seeds ou outros módulos.

Bcrypt considera no máximo os primeiros 72 bytes da senha. O login e a geração de hash rejeitam entradas acima de 72 bytes UTF-8 antes de chamar bcrypt; não truncam, normalizam nem removem espaços. O limite é em bytes, não em caracteres: por exemplo, 36 caracteres `é` ocupam 72 bytes em UTF-8. Hashes antigos podem ter sido criados com senhas maiores que esse limite, que bcrypt 4.0.1 truncava silenciosamente. Esses usuários precisarão redefinir a senha; nenhuma redefinição é feita automaticamente. O algoritmo e o formato dos hashes existentes permanecem inalterados.

Os testes de login usam hashing e assinatura JWT reais, substituindo somente a persistência por doubles. Eles não validam a conexão nem o esquema de um PostgreSQL real. A integração com PostgreSQL precisa ser validada separadamente num ambiente configurado. A validação Bearer para rotas protegidas fica para a SCRUM-8.

Gere uma chave JWT localmente com:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o resultado para `JWT_SECRET_KEY` no `.env`. Não compartilhe o segredo nem o inclua no controle de versão.

## Executar

```powershell
python -m uvicorn app.main:app --reload
```

- OpenAPI: <http://127.0.0.1:8000/docs>
- Saúde: <http://127.0.0.1:8000/health>

No startup, a aplicação valida a configuração obrigatória e prepara a engine sem abrir uma conexão. Importar os modelos para testes não exige credenciais. `/health` apenas confirma que a API está respondendo. A validação de configuração verifica formato e valores; ela não confirma que o servidor PostgreSQL está acessível.

Para verificar a conexão real manualmente, configure o `.env` e execute:

```powershell
python test_db.py
```

O script executa somente `SELECT 1`, encerra a conexão e retorna código diferente de zero em caso de falha. Esta verificação deve ser feita apenas contra um banco escolhido por você.

## Testes

Os testes unitários usam Settings PostgreSQL explícitas e sessões mockadas; não fazem conexão com banco real.

```powershell
python -m pytest -q
```
