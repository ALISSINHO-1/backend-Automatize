**Validação do backend do Automatize / PR #14 — 02/11/2026**

Atualização posterior: a pendência de `/auth/me` foi resolvida na mesma branch.
Veja a [integração e validação final](pr14-auth-me-validation-2026-11-02.md),
com 654 testes aprovados e classificação PRONTO PARA REVISÃO. O conteúdo abaixo
preserva o diagnóstico e os resultados da primeira etapa.

**Classificação: PARCIAL.** A correção do driver, a instalação limpa, as migrations
e todos os testes PostgreSQL passaram. A validação solicitada de `/auth/me` não
pode ser aprovada: essa rota e seus testes não existem no commit atual. O GET
retorna 404. Não foi acrescentada uma funcionalidade de autenticação a esta
correção de configuração.

Evidências consolidadas, versões completas das dependências, hashes dos arquivos
testados e contagens por módulo: [JSON da validação](pr14-validation-2026-11-02.json).
Os resultados abaixo foram executados nesta sessão; relatórios anteriores não
foram usados como comprovação de aprovação.

**1. Causa das duas falhas**

`requirements.txt` permite `sqlalchemy>=2.0.28` e instala
`psycopg2-binary>=2.9.9`. A instalação limpa resolveu SQLAlchemy **2.1.6**, cujo
dialeto padrão de `postgresql://` é `sqlalchemy.dialects.postgresql.psycopg`.
O ambiente anterior possuía SQLAlchemy **2.0.52**, cujo padrão era `psycopg2`.
O pacote `psycopg` não foi instalado pelo projeto nem adicionado nesta sessão.

Não foi encontrada uma transformação literal para `postgresql+psycopg://`
no código executável. A seleção ocorria dentro do SQLAlchemy: em
`app/core/config.py`, `validate_database_url` aceitava a URL genérica e a
devolvia sem explicitar o driver. `app/core/database.py: create_database_engine`
repassava essa URL a `create_engine`. O Alembic consumia a mesma validação em
`alembic/env.py`; a fixture PostgreSQL usava `TEST_DATABASE_URL` diretamente.

As falhas reproduzidas antes de editar código foram:

- `tests/test_postgres_tls.py::test_final_driver_parameters_are_checked_before_network`;
- `tests/test_postgres_tls.py::test_local_factory_options_remain_available_without_connection`.

Ambas falhavam em `PGDialect_psycopg.import_dbapi`, com
`ModuleNotFoundError: No module named 'psycopg'`, antes de qualquer conexão.

A primeira execução diagnóstica completa teve 496 passed / 3 failed / 127 skipped:
o lançador também havia exportado `DATABASE_URL`, interferindo no teste que
espera configuração ausente. Sem essa variável, esse teste passou sem mudanças
de código; a reprodução dirigida ficou em **2 failed / 1 passed**. Na execução
final, `DATABASE_URL` não foi exportada globalmente ao pytest; a fixture exporta
temporariamente a URL local apenas para o Alembic e restaura o ambiente depois.

Foram examinados requirements, `.env.example`, configuração, engines/sessões,
Alembic, migrations, testes, scripts e o utilitário `test_db.py`. Não há
`create_async_engine` no backend versionado. A cópia local ignorada
`backend-Automatize-HML` também foi pesquisada e permaneceu intacta.

**2. Arquivos alterados**

| Arquivo | Alteração |
| --- | --- |
| `app/core/config.py` | Define explicitamente `postgresql+psycopg2` no validador central. |
| `scripts/isolated_database.py` | Reutiliza o validador e devolve a URL normalizada, mantendo o bloqueio de destinos não locais. |
| `tests/integration/conftest.py` | Usa a URL validada no engine PostgreSQL e na configuração temporária do Alembic. |
| `tests/test_config_database.py` | Cobre os dois formatos aceitos, DBAPI efetiva, escapes, parâmetros e idempotência. |
| `tests/test_storage_reconciliation.py` | Cobre o retorno normalizado do guard de isolamento. |
| `tests/integration/test_migration_upgrade.py` | Executa a atualização de schema e a revogação de privilégios com ambos os formatos de URL. |
| `README.md` | Documenta a normalização e os requisitos do banco descartável. |
| `docs/pr14-validation-2026-11-02.md` | Este relatório. |
| `docs/pr14-validation-2026-11-02.json` | Evidências sem credenciais. |

Nenhuma migration, dependência, regra de negócio ou configuração de Supabase foi
alterada. Os arquivos não rastreados que já existiam foram preservados.

**3. Como o driver foi padronizado**

`validate_database_url` usa `make_url(...).set(drivername="postgresql+psycopg2")`
antes de renderizar a URL para SQLAlchemy. Esse é o único ponto de normalização.
A API e o Alembic já chamam esse validador. O guard dos scripts/testes agora
também o chama; a fixture utiliza o retorno, em vez da URL original.

Continuam aceitos `postgresql://` e `postgresql+psycopg2://`. Drivers explícitos
diferentes continuam rejeitados. Senhas escapadas, host, porta, nome do banco e
opções de conexão são preservados. TLS remoto obrigatório, proteção contra
sobrescrita de parâmetros e isolamento do banco de teste foram preservados.
Não houve substituição em massa nas migrations nem instalação de psycopg v3.

**4. DATABASE_URL utilizada**

`postgresql+psycopg2://***:***@127.0.0.1:55417/automatize_pr14_test`

Usada apenas no processo das verificações Alembic e nas aplicações locais
injetadas. Também foi verificada a entrada equivalente `postgresql://`:
ambas criaram engine `postgresql+psycopg2`, carregaram a DBAPI `psycopg2`,
executaram `SELECT 1` no banco descartável e responderam 200 em `/health`.
O `.env` existente não foi alterado nem seus valores publicados.

**5. TEST_DATABASE_URL utilizada**

Na suíte completa:
`postgresql+psycopg2://***:***@127.0.0.1:55417/automatize_pr14_test`.

Na verificação complementar de compatibilidade:
`postgresql://***:***@127.0.0.1:55417/automatize_pr14_test`.

As credenciais aleatórias ficaram somente no ambiente dos processos e em
arquivo local ignorado pelo Git, em `.pytest_tmp_pr14/`. A URL real não foi
incluída em nenhum arquivo a versionar. O contêiner exclusivo desta sessão é
`automatize-pr14-postgres17`, imagem `postgres:17`, porta publicada somente em
loopback. Nenhum banco existente foi reutilizado.
Após concluir as verificações, esse contêiner foi parado (`exited`), mantendo
somente seus dados locais para reprodução; nenhum contêiner existente foi alterado.

**6. Versões do ambiente**

| Componente | Versão |
| --- | --- |
| Python | 3.14.7, Windows x64 |
| SQLAlchemy | 2.1.6 |
| Alembic | 1.20.1 |
| psycopg2-binary | 2.9.13 |
| PostgreSQL | 17.11, Debian 17.11-1.pgdg13+2 |
| pytest | 9.2.0 |
| FastAPI | 0.162.0 |
| Starlette / HTTPX | 1.10.0 / 0.28.1 |

Foi criado um venv novo em `.pytest_tmp_pr14/venv`, com
`include-system-site-packages = false`. `python -m pip install -r requirements.txt`
terminou com código 0 e instalou todas as dependências sem herdar pacotes do
venv anterior. `python -m pip check`: **No broken requirements found.**

**7. Resultado do Alembic**

| Comando no banco descartável | Resultado |
| --- | --- |
| `python -m alembic upgrade head` | Código 0; sete revisões aplicadas a banco vazio. |
| `python -m alembic current` | `b6e1c8a4d230 (head)` |
| `python -m alembic heads` | `b6e1c8a4d230 (head)`; um único head. |
| `python -m alembic check` | Código 0; `No new upgrade operations detected.` |

**current == head confirmado.** O teste de upgrade também cria bancos vazios
auxiliares dentro do mesmo PostgreSQL descartável, simula privilégios legados,
aplica o hardening, verifica a preservação dos dados e executa `alembic check`.
Passou com URL genérica e com psycopg2 explícito.

**8. Resultado da suíte completa**

Comando executado no venv novo:

```text
python -m pytest tests -q -o cache_dir=.pytest_tmp_pr14/full-cache --basetemp=.pytest_tmp_pr14/full-tmp --junitxml=.pytest_tmp_pr14/full.xml
633 passed, 1 warning in 99.15s
```

Os argumentos extras apenas isolam temporários/cache e geram evidência JUnit.
Não houve filtro de seleção, exclusão ou supressão de warnings nessa execução.
O cache isolado evita um problema de permissão no cache antigo do workspace.

**9. Passed / failed / skipped / warnings**

| Execução | Passed | Failed | Errors | Skipped | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Suíte completa, TEST_DATABASE_URL com psycopg2 | 633 | 0 | 0 | 0 | 1 |
| Integração complementar, TEST_DATABASE_URL genérica | 128 | 0 | 0 | 0 | 1 |
| Configuração, TLS, isolamento e constraints/migrations offline | 86 | 0 | 0 | 0 | 0 |

As execuções se sobrepõem; os totais não devem ser somados. Não houve skip,
inclusive por ausência de TEST_DATABASE_URL; não existem skips individuais a
justificar. O warning da suíte final é `StarletteDeprecationWarning`: o uso de
HTTPX com TestClient está depreciado. Não é falha de driver, schema ou negócio.

**10. Resultado dos testes PostgreSQL**

**128 passed / 0 failed / 0 skipped** na suíte completa, repetidos com sucesso
com a URL genérica (32,70 s na execução complementar).

| Módulo em `tests/integration` | Passed | Cobertura principal |
| --- | ---: | --- |
| `test_attachment_storage_transactions` | 4 | Anexos e compensação/rollback. |
| `test_concurrency_postgres` | 6 | Concorrência, locks, aceite único e liberação de transação. |
| `test_demand_service_db` | 47 | Persistência via repositories, etapas, histórico, autorização, aceite e auditoria. |
| `test_demandas_acoes_api` | 10 | Rotas JWT, etapas, autorização e homologação. |
| `test_hml_dataset` | 2 | Massa sintética e rollback no banco isolado. |
| `test_legacy_update_authorization` | 8 | ADMIN/TECNICO/CLIENTE e bloqueio de bypass. |
| `test_migration_upgrade` | 2 | Upgrade real, constraints/modelos e grants/revokes, nos dois formatos de URL. |
| `test_postgres_security` | 28 | RLS, privilégios, triggers, search_path e auditoria imutável. |
| `test_scrum71_homologacao` | 18 | Matriz obrigatória de homologação nos services e na API. |
| `test_user_queries_api` | 3 | Escopo e permissões nas consultas de usuários. |

Os testes de `tests/repositories` somam **73 passed** e usam SQLite; são
complementares, não substitutos dos 128 testes PostgreSQL reais. Os dois testes
de `tests/test_migrations_constraints.py` verificam DDL/constraints/FKs. A
inspeção real de `pg_constraint` confirmou **16 foreign keys** no PostgreSQL,
e `alembic check` confirmou a correspondência do schema com os modelos.

**11. Homologação / SCRUM-71**

| Cenário obrigatório | Resultado no PostgreSQL real |
| --- | --- |
| Demanda sem etapas | Bloqueada; seis verificações entre estados e entradas. |
| Uma etapa pendente | Bloqueada; três verificações. |
| Múltiplas etapas com alguma pendente | Bloqueada; três verificações. |
| Ao menos uma etapa e todas concluídas | Permitida; seis verificações. |

**18 passed**, exercitando DemandService, PedidoService e API com JWT. As
recusas também preservam status, progresso, histórico e auditoria. Nenhum
arquivo das regras de ciclo de vida ou dos services foi alterado.

**12. Permissões / RLS / segurança**

**28 testes PostgreSQL de segurança aprovados**, além dos dois upgrades reais
e dos testes de autorização citados acima. Foram confirmados:

- RLS habilitada em todas as nove tabelas, incluindo `historico_status_pedidos`,
  `etapas_operacionais` e `alembic_version`;
- grants de tabela/coluna fechados para `anon` e `authenticated`, com operações
  reais recusadas com SQLSTATE 42501;
- RLS bloqueando linhas existentes mesmo após GRANT SELECT temporário;
- `bloquear_alteracao_aceite_formal`, `proteger_conclusao_pedido` e
  `proteger_auditoria_log` como SECURITY INVOKER, sem EXECUTE para as roles
  públicas de cliente, com `search_path=pg_catalog, pg_temp`;
- aceite formal imutável, conclusão sem aceite bloqueada, resistência a tabela
  temporária maliciosa e auditoria protegida contra UPDATE/DELETE;
- preservação do payload de auditoria quando uma FK é desvinculada por exclusão
  legítima do registro pai.

As roles de cliente foram criadas somente no cluster Docker descartável. A
conexão administrativa desse cluster não equivale à role de implantação do
Supabase. Nenhuma conexão, migration ou mudança foi feita no Supabase compartilhado.

**13. Resultado de /auth/me**

**Ausente neste código; GET retorna 404.** O OpenAPI publica somente
`/auth/login` sob `/auth`; `tests/test_main.py` também espera esse contrato.
Não há testes de `/auth/me` nesta branch. Os **26 testes de login** e os
**16 testes de autenticação/autorização de demandas** passaram.

A consulta somente de leitura ao [PR #14](https://github.com/ALISSINHO-1/backend-Automatize/pull/14)
confirmou o mesmo head local `da7e4285d4fd7f0c6f9e290adb18c8aacdd77bf2`,
branch `Henrique-Silva`. Portanto, não é correto declarar aprovados testes de
uma rota ausente. Essa divergência do contexto informado permanece registrada.

**14. Possíveis regressões e limites**

Nenhuma regressão foi observada na suíte existente e nos casos acrescentados.
A normalização passa a devolver sempre a forma explícita da URL; testes de
igualdade textual foram ajustados para comparar os componentes esperados. As
credenciais escapadas e opções de conexão estão cobertas por regressão.

Os limites são a ausência de `/auth/me`, o warning externo de TestClient e a
validação restrita ao PostgreSQL descartável. O Storage foi substituído por
fakes nos testes transacionais; o Storage e as permissões efetivas do Supabase
compartilhado não foram exercitados. Os limites abertos de versões em
requirements permanecem; as versões efetivamente testadas estão registradas.

**15. Qualidade e git status final**

`git diff --check` e `git diff --cached --check` passaram. A busca por
marcadores de conflito no backend versionado não encontrou ocorrências. O
scanner de segredos retornou **zero arquivos versionados com correspondência
potencial** e **zero arquivos de bytecode versionados**; apontou apenas o
`.env` local preexistente, ignorado. Nenhum `.env`, `.pyc`, `__pycache__`,
credencial, senha real, token ou chave Supabase foi acrescentado aos artefatos
para revisão. Os temporários ficaram sob `.pytest_tmp_pr14/`, ignorado pelo Git.

```text
 M README.md
 M app/core/config.py
 M scripts/isolated_database.py
 M tests/integration/conftest.py
 M tests/integration/test_migration_upgrade.py
 M tests/test_config_database.py
 M tests/test_storage_reconciliation.py
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/pr14-validation-2026-11-02.json
?? docs/pr14-validation-2026-11-02.md
?? frontend-Automatize-HML/
```

Os três patches, `docs/evidence/` e `frontend-Automatize-HML/` já estavam não
rastreados no início e foram preservados. Nada foi staged. Não houve commit,
push, merge, troca de branch ou alteração de refs nesta sessão.

**16. Commit atual testado**

`da7e4285d4fd7f0c6f9e290adb18c8aacdd77bf2`, branch **Henrique-Silva**, mais as
alterações locais descritas neste relatório. O resultado de 633 testes se refere
ao working tree corrigido; não ao commit original sem a correção. O JSON anexo
registra SHA-256 dos sete arquivos modificados de implementação/testes/documentação
que estavam presentes durante a execução.
