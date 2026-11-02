**SCRUM-82 / SCRUM-103 — auditoria e validação de segurança — 02/11/2026**

| Tarefa | Classificação global | Implementado em código | Testado localmente | Aplicado no Supabase |
| --- | --- | --- | --- | --- |
| SCRUM-82 | **PARCIAL** | Sim, proteções existentes preservadas. | Sim, PostgreSQL real. | **Não**; hardening ainda pendente. |
| SCRUM-103 | **PARCIAL** | Sim para tabelas/functions; Storage auditado, runtime restrito apenas proposto. | Sim, permissões reais e proposta de runtime. | **Não**; grants/defaults/runtime ainda exigem implantação/revisão. |

As proteções locais passaram. O estado compartilhado continua vulnerável aos
alertas citados; nenhuma alteração foi aplicada nele. Esta conclusão não usa
relatórios antigos como comprovação de execução atual.

[Evidências JSON](scrum82-103-validation-2026-11-02.json): snapshots de catálogos
somente leitura, contagens por módulo, versões, hashes dos oito arquivos
testados/alterados e distinção entre ambientes. Não contém connection strings,
senhas, JWTs, chaves, nomes/e-mails de usuários ou conteúdo de anexos.

**1. Commit-base analisado**

`7171c31cf8c5aa58de0bf77c14fc0bd974c2258d` — Corrige driver PostgreSQL e integra
endpoint auth me. O HEAD permaneceu nesse commit durante toda esta tarefa.
Os resultados finais correspondem ao working tree com as alterações descritas.

**2. Branch**

`Henrique-Silva`. Não houve checkout, alteração de main/HML, fetch, merge,
rebase, staging, commit ou push nesta tarefa.

**3. Estado inicial e auditoria antes de editar**

Não havia modificações rastreadas. Já existiam, não rastreados, três patches em
`docs/`, `docs/evidence/` e `frontend-Automatize-HML/`; todos foram preservados.

Foram lidos models, repositories, services, endpoints, SQLAlchemy/psycopg2,
configuração Supabase/Storage, cadeia Alembic, triggers/functions, grants,
policies e testes de segurança. A arquitetura encontrada é FastAPI/SQLAlchemy
para as tabelas de domínio; Supabase SDK é usado para Storage. A autenticação
existente valida JWT e carrega o usuário ativo; autorização e autoria são
definidas pelos services, sem confiar em IDs do corpo da requisição.

Foram executadas inspeções reais no Supabase somente com SELECT/SHOW em
transação READ ONLY e GET dos metadados do bucket. A versão é PostgreSQL 17.6,
revisão Alembic `3c9e7a1b5d20`. Não foram exportados registros pessoais.

**4. Problemas encontrados**

| Achado atual no Supabase | Situação |
| --- | --- |
| `etapas_operacionais`, `historico_status_pedidos`, `alembic_version` sem RLS | Confirmado por catálogo. |
| Grants efetivos amplos para anon/authenticated nas nove tabelas | Confirmados: CRUD, TRUNCATE, REFERENCES, TRIGGER e MAINTAIN. |
| Duas funções sem search_path fixo | `proconfig` nulo; EXECUTE efetivo para roles de cliente. |
| Proteção append-only da auditoria ainda ausente | Function/trigger de `b6e1c8a4d230` não estão implantadas. |
| Backend SQL excessivamente privilegiado | BYPASSRLS, CREATEROLE, CREATEDB e ownership; não é superuser. |
| Defaults amplos para futuros objetos | Confirmados em public/storage, para tabelas, sequences e functions. |
| Bucket sem limite próprio de tamanho/MIME | Metadados mostram ambos não configurados; validação da API continua existente. |

PUBLIC não tinha grants explícitos de tabela/coluna nas tabelas auditadas;
o problema de acesso efetivo estava em anon/authenticated. Nenhuma policy foi
encontrada em public/storage. As roles de cliente não tinham CREATE em public,
CREATE no banco, BYPASSRLS ou membership da role do backend.

O auditor anterior omitia MAINTAIN, privilégio de PostgreSQL 17. A inspeção e a
avaliação foram ampliadas, com oito novos casos unitários. O `REVOKE ALL` da
migration existente já remove esse privilégio nas tabelas atuais; não foi
necessário criar outra migration equivalente. [Privilégios PostgreSQL 17](https://www.postgresql.org/docs/17/ddl-priv.html).

Também foi encontrada uma falha no helper de testes de concorrência: `SET`
persistia timeouts curtos nas conexões retornadas ao pool, cancelando um
CREATE DATABASE posterior. A correção usa SET LOCAL, mantendo o limite apenas
na transação do worker. A regressão dirigida e a suíte final passaram.

**5. Arquivos modificados**

| Arquivo | Alteração |
| --- | --- |
| `app/infrastructure/database/data_api_security.py` | Inspeção/avaliação de MAINTAIN, com condição de versão. |
| `scripts/audit_technical_state.py` | Conexão READ ONLY desde o início, timeouts, PUBLIC/colunas, defaults, roles, triggers, três functions, clauses de policies e grants Storage; ausência de Storage agora é explícita. |
| `tests/test_data_api_security.py` | Regressões para MAINTAIN em roles de cliente. |
| `tests/integration/test_postgres_security.py` | INSERT/TRUNCATE/ALTER reais negados, além dos casos existentes; terceira function auditada. |
| `tests/integration/test_security_runtime_role.py` | Novo: 16 casos de runtime sem ownership/DDL e auditoria real somente leitura. |
| `tests/integration/test_concurrency_postgres.py` | Isolamento transacional dos timeouts do helper. |
| `docs/security/persistence-hardening.md` | Estado atual e separação do texto histórico desatualizado. |
| `docs/security/data_api_hardening.sql` | Aviso de artefato histórico substituído pela migration integrada; SQL não executado. |
| `docs/scrum82-103-validation-2026-11-02.md` | Este relatório. |
| `docs/scrum82-103-validation-2026-11-02.json` | Evidências sem credenciais. |

Não houve alteração em models, repositories, services, endpoints, autenticação,
driver/configuração, código de Storage ou regras de negócio.

**6. Migration criada/modificada**

**Nenhuma.** A equivalência foi verificada antes de editar:

```text
fbfba8e84540 -> a4fa37701385 -> fd3fe1dcfeab -> 3c9e7a1b5d20
-> 7b2d4e6f8a10 -> 9d4f2a6c8e11 -> b6e1c8a4d230 (head)
```

`3c9e7a1b5d20` já cria unicidade do aceite e triggers de imutabilidade/conclusão.
`7b2d4e6f8a10` habilita RLS nas nove tabelas. `9d4f2a6c8e11` fixa search_path e
revoga grants de tabelas/colunas e EXECUTE. `b6e1c8a4d230` protege a auditoria,
permitindo apenas desvinculação legítima por FK SET NULL sem adulterar payload.

Essas migrations preservam os dados e a regra da SCRUM-71. Repetir upgrade head
é um no-op quando já aplicado; as operações idempotentes existentes usam ENABLE
RLS, REVOKE e CREATE OR REPLACE quando apropriado. Não se exige replay manual
do CREATE FUNCTION de uma revisão já controlada por Alembic.

**7. RLS antes/depois: comparação de ambientes, sem mudança no real**

| Tabelas | Supabase observado READ ONLY | PostgreSQL descartável após migrations |
| --- | --- | --- |
| etapas, histórico de status e alembic_version | Desabilitada | Habilitada |
| users, pedidos, ocorrencias, anexos, aceites, auditoria | Habilitada | Habilitada |
| storage.objects / storage.buckets | Habilitada | Serviço/schema Storage ausente, explicitamente não validado localmente. |

Não foi usado FORCE RLS sobre o owner. Sem policies, RLS nega acesso a linhas
às roles sujeitas a ela. TRUNCATE/REFERENCES não são cobertos por RLS: os testes
verificam privilégios e operações separadamente. [RLS PostgreSQL](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

**8. GRANT/REVOKE antes/depois**

Nas nove tabelas atuais, o Supabase ainda apresenta privilégios amplos de
anon/authenticated. No banco descartável, a cadeia existente retirou todos os
grants de tabela e coluna dessas roles e de PUBLIC, incluindo MAINTAIN em PG17.
SELECT, INSERT, UPDATE, DELETE, TRUNCATE e ALTER TABLE foram realmente tentados
pelas roles de cliente e recusados com SQLSTATE 42501, somente no Docker.

O upgrade de banco existente simulou grants legados de tabela/coluna, preservou
dados e grants de service_role, retirou acesso de clientes e passou no check.
Em PostgreSQL comum, a role service_role criada para testes não recebe grants
automaticamente; isso não é apresentado como réplica dos defaults do provedor.

Uma proposta de runtime foi testada sem ownership, SUPERUSER, CREATEROLE,
CREATEDB ou CREATE no schema; manteve BYPASSRLS para a arquitetura backend-only.
Ela recebeu apenas SELECT/INSERT em aceite, auditoria e histórico, e CRUD nas
demais tabelas de domínio. Não recebeu acesso a alembic_version, DDL ou TRUNCATE.
O ciclo operacional e o aceite continuaram funcionando. A role e seus grants
foram revertidos pela transação do teste; não foram implantados.

**9. Policies criadas**

**Nenhuma.** Não há consumidor legítimo identificado da Data API para essas
tabelas. Criar policies permissivas para silenciar o Advisor enfraqueceria o
isolamento. Nenhuma policy do schema gerenciado Storage foi criada/removida.

**10. Functions corrigidas e triggers**

A correção já está em `9d4f2a6c8e11`, preservada sem duplicação:

- `public.bloquear_alteracao_aceite_formal`: rejeita UPDATE/DELETE;
- `public.proteger_conclusao_pedido`: referencia `public.aceites_formais`, exige
  aceite para concluir e bloqueia alteração/exclusão de pedido concluído.

No PostgreSQL local, ambas têm SECURITY INVOKER e
`search_path=pg_catalog, pg_temp`, sem EXECUTE para clientes. A terceira,
`public.proteger_auditoria_log`, tem as mesmas proteções. Os três triggers estão
presentes e habilitados. O teste com tabela temporária maliciosa não conseguiu
contornar a conclusão; UPDATE/DELETE do aceite e adulteração da auditoria foram
recusados. CREATE OR REPLACE preserva dependências/ownership da função.
[CREATE FUNCTION PostgreSQL](https://www.postgresql.org/docs/17/sql-createfunction.html).

No Supabase, as duas funções antigas continuam sem configuração de search_path
e o trigger de auditoria ainda não existe. Não foram corrigidos no ambiente real.

**11. Resultado SCRUM-82**

**PARCIAL global; implementação e validação local aprovadas.** Aceite único,
imutabilidade de aceite/auditoria, conclusão sem aceite bloqueada, preservação
de evidências e rollback foram comprovados. O histórico não ganhou uma regra
nova de imutabilidade administrativa: usuários comuns são restringidos por
grants/RLS/API; a proposta de runtime também nega UPDATE/DELETE do histórico.

Os agregados READ ONLY do real retornaram zero conclusões sem aceite, zero
aceites duplicados e zero pares anexo/ocorrência de pedidos diferentes. Isso
não equivale a certificar todo o histórico ou impedir futuras adulterações:
o hardening da auditoria ainda não está aplicado e a role administrativa segue
privilegiada. A implantação permanece pendente.

**12. Resultado SCRUM-103 e Storage**

**PARCIAL.** Isolamento de domínio implementado/testado, ainda não implantado.
Revisão da role de runtime e dos defaults do provedor permanece necessária.

O código seleciona o bucket por STORAGE_BUCKET_NAME (default público no código:
`evidencias-anexos`); o valor do ambiente não foi exportado. O bucket configurado
foi encontrado privado; storage.objects/buckets têm RLS; não foram encontradas
policies para clientes, nem grants de TRUNCATE para anon/authenticated nesses
objetos. O SDK configurado conseguiu ler os metadados privados do bucket.

Os grants CRUD existentes em Storage não permitem concluir, isoladamente, que
há bypass: com RLS e ausência de policies, a inferência é default-deny para
clientes sem bypass. Não se fez teste real de upload, exclusão ou download de
objeto. Não se afirma uma negação HTTP de escrita medida. A leitura privada e
as regras de upload seguem a documentação de
[buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals) e
[controle de acesso](https://supabase.com/docs/guides/storage/security/access-control).

Na API, o usuário/escopo é verificado antes do upload, o caminho é gerado como
pedidos/UUID/UUID.ext, o conteúdo é validado e upsert está desabilitado. UUID de
caminho não substitui autorização. O schema privado não oferece acesso de um
cliente a anexos de outro por policy encontrada. Credenciais privilegiadas
continuam uma fronteira de confiança e não devem chegar ao Flutter.

Não houve limpeza de órfãos, envio, download ou exclusão de arquivos. SCRUM-87
permaneceu fora do escopo. Não foi preparada migration de Storage porque não
foi identificado acesso permissivo de cliente a corrigir; limites do bucket e
separação de credenciais foram documentados para revisão, sem mudança no provedor.

**13. Resultado SCRUM-71**

**18 testes de matriz PostgreSQL aprovados**, mais a validação do fluxo pela
role restrita. Sem etapas: bloqueada. Uma etapa pendente: bloqueada. Várias
com alguma pendente: bloqueada. Uma ou mais, todas concluídas: permitida.
Nenhuma regra foi inventada, removida ou afrouxada para satisfazer testes.

**14. Testes PostgreSQL e regressões dirigidas**

**152 passed / 0 failed / 0 errors / 0 skipped**, incluídos na suíte completa.
São os 136 anteriores mais 16 de runtime/catálogo. As execuções dirigidas foram:

| Conjunto | Passed | Failed / errors / skipped | Warnings |
| --- | ---: | --- | ---: |
| Segurança, permissões, MAINTAIN, upgrade e SCRUM-71 | 123 | 0 / 0 / 0 | 1 |
| Concorrência + seed HML + upgrade, após corrigir SET LOCAL | 10 | 0 / 0 / 0 | 0 |

Os conjuntos se sobrepõem e não devem ser somados. A cobertura inclui banco
vazio, upgrade com dados, bloqueio anon/authenticated, PUBLIC, histórico, etapas,
alembic_version, role autorizada, aceite UPDATE/DELETE, auditoria, shadowing,
rollback, concorrência, autenticação/autorização e regressão de `/auth/me`.

**15. Suíte completa final**

```text
python -m pytest tests -q
678 passed, 1 warning in 139.19s
```

Executada com TEST_DATABASE_URL definida exclusivamente para banco novo no
PostgreSQL 17.11 descartável, com guard de loopback/porta/nome de testes.
Os argumentos adicionais apenas isolam cache/temporários e geram JUnit em
`.pytest_tmp_pr14/`. Não houve filtro ou supressão de testes/warnings.
**0 failed, 0 errors, 0 skipped.** Não há skips individuais a justificar.
O warning é depreciação externa de HTTPX no Starlette TestClient.

Uma rodada intermediária teve 1 falha por timeout herdado do pool; não foi
contada como aprovada. A causa foi corrigida no helper e a suíte completa
foi repetida com sucesso. Os detalhes estão no JSON.

**16. Alembic current/head/check**

| Verificação no banco descartável | Resultado |
| --- | --- |
| upgrade head em banco novo e vazio | Sete revisões aplicadas; código 0. |
| current | `b6e1c8a4d230 (head)` |
| heads | `b6e1c8a4d230 (head)`, único head. |
| check | `No new upgrade operations detected.` |
| upgrade existente com privilégios legados | Dois casos aprovados, preservando dados e service_role. |
| pip check | `No broken requirements found.` |

Python 3.14.7, SQLAlchemy 2.1.6, Alembic 1.20.1 e psycopg2-binary 2.9.13.
Não foi executado upgrade/stamp/downgrade no Supabase.
O check final após a suíte também passou. A inspeção local confirmou zero roles
temporárias de runtime remanescentes. O contêiner descartável foi parado
(`exited`), preservando somente seus dados locais para reprodução.

**17. Impacto esperado na API**

Nenhuma mudança de contrato ou de regra. `/auth/me`, login e autorizações
passaram. O módulo alterado só avalia catálogos; não muda grants em runtime.
Quando implantadas, as migrations existentes devem preservar a conexão SQL
autorizada e obrigar clientes a passar pelo FastAPI. A role restrita demonstrada
é uma proposta local, não uma troca automática da conexão da aplicação.

**18. Impacto esperado no Flutter**

Nenhum arquivo alterado. O frontend que utiliza HTTP/Bearer mantém o contrato.
Qualquer consumidor externo desconhecido que dependa de acesso direto às
tabelas deve ser revisado antes da implantação; esse acesso será bloqueado.

**19. Impacto esperado no Storage**

Nenhuma configuração ou objeto alterado. Bucket privado e policies atuais
foram apenas auditados. Os testes locais de Storage usam doubles e verificam
compensações/escopo, não são apresentados como Supabase Storage real. Fluxo de
download autorizado e segurança de distribuição de credenciais não foram
certificados por um ensaio completo de Storage nesta tarefa.

**20. O que depende de implantação no Supabase**

Revisar e implantar a cadeia já existente após `3c9e7a1b5d20`, com backup e
revisão operacional próprios. Depois confirmar RLS, grants efetivos/colunas,
EXECUTE/search_path, trigger de auditoria e Advisor. Separar runtime/migrator e
revisar defaults por creator/schema sem alterar indiscriminadamente o schema
gerenciado Storage. Nada disso foi executado ou automaticamente agendado.

**21. Riscos restantes e limites**

O Supabase mantém os alertas e permissões observados. Owner/BYPASSRLS não é
isolado como um cliente comum; owner pode administrar triggers e reatribuir
grants. O banco não interpreta o JWT da aplicação: autoria e máquina de estados
continuam responsabilidade da API além das constraints/triggers existentes.
Defaults amplos podem reabrir acesso em novas tabelas/functions se futuras
migrations não fizerem hardening. Revogar ALL nas tabelas atuais não muda todos
os defaults do provedor.

O bucket não tem limites próprios de tamanho/MIME. Uma credencial privilegiada
comprometida pode contornar a validação da API. Não foram executados testes de
escrita no Storage real ou ataques na Data API real. As migrations de segurança
recusam downgrade automático; não inventar grants de rollback nem usar stamp
para contornar isso. Esses pontos impedem classificar as tarefas como concluídas
no ambiente compartilhado.

**22. git status final e qualidade**

`git diff --check` e `git diff --cached --check` aprovados. Sem marcadores de
conflito. Scanner: zero correspondências potenciais em arquivos versionados e
zero bytecode versionado; apenas o `.env` preexistente e ignorado foi apontado.
Nenhum segredo, connection string, `.env`, `.pyc` ou `__pycache__` foi adicionado.

```text
 M app/infrastructure/database/data_api_security.py
 M docs/security/data_api_hardening.sql
 M docs/security/persistence-hardening.md
 M scripts/audit_technical_state.py
 M tests/integration/test_concurrency_postgres.py
 M tests/integration/test_postgres_security.py
 M tests/test_data_api_security.py
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/scrum82-103-validation-2026-11-02.json
?? docs/scrum82-103-validation-2026-11-02.md
?? frontend-Automatize-HML/
?? tests/integration/test_security_runtime_role.py
```

Nada staged. Nenhum git add/commit/push/merge/rebase, nenhuma exclusão de dados
reais e nenhuma migration ou alteração de permissões no banco compartilhado.
