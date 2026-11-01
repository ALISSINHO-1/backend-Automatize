# Ambiente de demonstracao

O seed usa o banco configurado para o backend. Ele escreve dados permanentes
somente com `--apply`, sem aplicar migrations ou alterar contas existentes.
Nao execute contra producao. Os e-mails podem ser personalizados no `.env`.

## Credenciais

Configure localmente, sem enviar senhas para terminal/chat/Git:

```dotenv
DEMO_ADMIN_EMAIL=admin.demo@automatize.local
DEMO_ADMIN_PASSWORD=
DEMO_TECNICO_EMAIL=tecnico.demo@automatize.local
DEMO_TECNICO_PASSWORD=
DEMO_CLIENTE_EMAIL=cliente.demo@automatize.local
DEMO_CLIENTE_PASSWORD=
```

Cada senha e obrigatoria e deve respeitar o limite do bcrypt: ate 72 bytes
UTF-8. O hash usa `app.core.security.hash_password`, o mesmo mecanismo do login.
O `.env` nao deve ser versionado. O script nao imprime senhas, hashes ou tokens.

## Preparacao

```powershell
python -m alembic heads
python -m alembic current
python -m alembic history
python -m scripts.seed_demo_environment
```

O ultimo comando valida a configuracao sem escrever no banco.
Uma migration pendente deve ser revisada separadamente; o seed nunca executa
`upgrade`, `downgrade` ou `stamp`.

Apos conferir o destino e autorizar a escrita:

```powershell
python -m scripts.seed_demo_environment --apply
```

O seed cria, em uma transacao:

- ADMIN, TECNICO e CLIENTE ativos;
- pedido `DEMO-APRESENTACAO` em PLANEAMENTO, do CLIENTE e sob responsabilidade
  do TECNICO;
- ocorrencia ERRO vinculada ao pedido e ao CLIENTE como autor;
- registro de auditoria `SEED_DEMONSTRACAO`.

Usa os repositories reais. Nao exercita nem modifica transicoes de negocio.
Repetir o comando preserva IDs, hashes e edicoes feitas durante a apresentacao.
Uma conta existente com perfil, atividade, email ou senha incompativel bloqueia
o seed; nenhuma conta e reativada, promovida ou tem sua senha redefinida.
No PostgreSQL, um advisory lock transacional serializa execucoes concorrentes.

## Login e visibilidade

Use `POST /auth/login` com o email e a senha local. O JWT identifica o UUID;
o perfil e consultado do usuario ativo no banco, nao presumido pelo frontend.
Nao compartilhe a resposta contendo o token.

Em `GET /demandas`, usando Bearer:

- ADMIN consulta todas as demandas;
- TECNICO consulta somente pedidos com `responsavel_id` igual ao seu UUID;
- CLIENTE consulta somente pedidos com `cliente_id` igual ao seu UUID.

`GET /demandas/{id}` devolve 404 para pedidos fora do escopo.

## Limites do modelo e da apresentacao

Nao existe FK ADMIN -> TECNICO. `UserRepository.list_tecnicos()` oferece a
consulta de tecnicos, mas nao existe endpoint especifico de listagem de usuarios.
`list_clientes_por_responsavel()` relaciona clientes a tecnicos via pedidos.
Isso nao representa uma carteira permanente: um cliente pode ter pedidos com
tecnicos diferentes. Nao existe perfil EMPRESA no enum persistido atual.

O seed nao cria endpoints, telas Flutter nem atualizacao periodica. SCRUM-39
requer uma demonstracao especifica no aplicativo.

## Testes

```powershell
python -m pytest tests/test_demo_user_seed.py tests/test_auth_login.py tests/test_demandas_auth.py tests/repositories -q
python -m pytest tests -q
git diff --check
git status
```

Os novos testes usam SQL, FKs e autenticacao reais em SQLite isolado. Isso nao
substitui confirmar os mesmos dados em uma nova conexao PostgreSQL/Supabase.
Os testes em `tests/integration/` exigem banco PostgreSQL descartavel especifico;
nunca aponte `TEST_DATABASE_URL` para o banco compartilhado da demonstracao.
