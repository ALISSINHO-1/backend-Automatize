**Finalização técnica — Henrique / Automatize — 02/11/2026**

O backend está validado e pronto para revisão do código local: **701 passed,
0 failed, 0 errors, 0 skipped e 1 warning**, com **168 testes PostgreSQL reais**.
A finalização do projeto como um todo permanece parcial: o frontend disponível
é uma cópia não canônica que não compila, as migrations não foram aplicadas no
Supabase e a limpeza destrutiva de órfãos não foi implementada sem um protocolo
seguro de coordenação/versionamento.

[Evidências estruturadas](finalizacao-henrique-2026-11-02.json): versões,
catálogos READ ONLY, contagens por módulo, matriz de tickets, hashes dos arquivos,
lista de entrega e resultados Flutter. Nenhuma conexão, senha ou chave real é
incluída. Os relatórios anteriores não foram usados como prova da execução atual.

**1. Branch**

`Henrique-Silva`, mantida durante toda a sessão. Main/HML não foram alteradas.

**2. Commit-base**

`7171c31cf8c5aa58de0bf77c14fc0bd974c2258d`. O HEAD não mudou. As alterações
novas e as de SCRUM-82/103 continuam sem staging, commit ou push.

**3. Inventário Git inicial, antes de editar**

Foram executados status, diff --stat, diff --check, diff --name-only,
log -3 --oneline e branch --show-current. O diff check passou; nada staged.
Havia sete arquivos rastreados modificados, com 150 inserções e 16 remoções:

```text
app/infrastructure/database/data_api_security.py
docs/security/data_api_hardening.sql
docs/security/persistence-hardening.md
scripts/audit_technical_state.py
tests/integration/test_concurrency_postgres.py
tests/integration/test_postgres_security.py
tests/test_data_api_security.py
```

Esses arquivos e o teste não rastreado `test_security_runtime_role.py` pertencem
à entrega SCRUM-82/103: auditoria, MAINTAIN, privilégios, runtime restrito e
isolamento dos timeouts de concorrência. Já havia três patches, docs/evidence,
dois relatórios SCRUM-82/103 e a cópia Flutter não rastreados. Eles foram
preservados e separados da lista recomendada para o próximo commit.

Log inicial: `7171c31`, `da7e428`, `97bda2f`. Nenhum git add/commit/push/merge/rebase
foi executado nesta finalização.

**4. Arquivos modificados e separação da entrega**

Além da consolidação inicial, a entrega acrescenta integridade do vínculo de
anexos no PostgreSQL, recibos de inventário READ ONLY, restauração com comparação
de segurança e testes dessas condições. A lista exata dos **23 arquivos** está
ao final. Nenhum arquivo Dart original foi modificado; 43 hashes de fontes
foram conferidos antes/depois.

**5. Migrations**

Nova revisão **`d8f4a2c6e901`**, descendente de `b6e1c8a4d230`. Nenhuma migration
antiga foi alterada e nenhum hardening equivalente foi duplicado.

A API já impedia ocorrência de outro pedido; faltava a garantia relacional
contra SQL direto. A revisão adiciona UNIQUE(id, pedido_id) em ocorrencias e FK
composta de anexos(ocorrencia_id, pedido_id). As FKs antigas permanecem: pedido
CASCADE e ocorrência SET NULL. A FK composta é DEFERRABLE INITIALLY DEFERRED,
validada no COMMIT ou explicitamente com SET CONSTRAINTS IMMEDIATE, depois da
ação referencial SET NULL. Essa escolha preserva as regras de exclusão existentes.

O preflight aborta diante de vínculos legados inconsistentes sem reparar,
apagar ou exportar linhas. Casos de upgrade com dados válidos e inválidos foram
executados. O downgrade automático é recusado e exige plano revisado.
O comportamento de constraints diferidas está documentado pelo
[PostgreSQL](https://www.postgresql.org/docs/17/sql-set-constraints.html).

**6. Alembic**

| Verificação local | Resultado |
| --- | --- |
| Upgrade de banco vazio | Oito revisões aplicadas, código 0. |
| Heads | Uma única head: `d8f4a2c6e901`. |
| Current | `d8f4a2c6e901 (head)`. |
| Check | `No new upgrade operations detected.` |
| History | Cadeia linear desde fbfba8e84540, registrada no JSON. |
| Upgrade existente | Grants/dados preservados; preflight inconsistente abortou sem correção automática. |
| Check no banco restaurado | Aprovado, sem operações novas. |

Não houve upgrade, stamp ou downgrade no Supabase compartilhado.

**7. PostgreSQL e ambiente**

PostgreSQL **17.11** em contêiner novo, `automatize-final-20261102`, publicado
somente em loopback:55427 e com banco vazio de testes. A credencial aleatória
ficou somente no ambiente e em arquivo ignorado. TEST_DATABASE_URL foi definida
exclusivamente para esse alvo; a conexão nunca foi direcionada ao Supabase.

Python 3.14.7, SQLAlchemy 2.1.6, Alembic 1.20.1 e psycopg2-binary 2.9.13.
Foi reutilizado o venv isolado da instalação limpa, sem pacotes globais.
`pip check`: **No broken requirements found.** Nenhuma dependência foi alterada.

**8. Suíte completa**

```text
python -m pytest tests -q --tb=short
701 passed, 1 warning in 171.80s
```

Os argumentos adicionais apenas isolam cache/temporários e geram JUnit no
diretório ignorado. Não houve filtro da suíte completa nem supressão de warnings.
**0 failed / 0 errors / 0 skipped.** Nenhum skip PostgreSQL foi contado como
aprovado. Não há grupos ignorados a justificar. O warning é depreciação externa
de HTTPX no Starlette TestClient.

**9. Testes PostgreSQL e grupos funcionais**

**168 passed**, incluídos nos 701. A execução focada anterior passou com
**50 testes**, e os testes de repositories/metadata passaram com **75**.
Conjuntos sobrepostos não devem ser somados.

| Grupo PostgreSQL | Passed |
| --- | ---: |
| Integridade de anexos / nova migration / transações Storage simulado | 8 / 2 / 4 |
| /auth/me com login real | 8 |
| Concorrência | 6 |
| DemandService persistido / rotas JWT | 47 / 10 |
| Massa HML / autorização legada / upgrade de segurança | 2 / 8 / 2 |
| RLS, grants, funções e EXECUTE | 34 |
| Runtime restrito e auditoria de catálogo | 16 |
| Consultas de usuários | 3 |
| Matriz SCRUM-71 | 18 |

Autenticação, autorização, repositories, services, constraints, drivers/TLS,
Storage, validação de conteúdo e scripts também passaram na suíte completa.
As permissões de MAINTAIN foram verificadas pelo catálogo PG17; não se alega
execução de VACUUM/REINDEX no ambiente compartilhado.

**10. SCRUM-71**

Os **18 testes** de services/API/PostgreSQL confirmaram: sem etapas bloqueia;
uma etapa pendente bloqueia; múltiplas com alguma pendente bloqueiam; uma ou
mais e todas concluídas permitem HOMOLOGACAO. O fluxo também funcionou com a
role restrita proposta. Não houve mudança de regra de homologação.

**11. Segurança / SCRUM-82**

Aceite formal continuou imutável no ORM e no banco; UPDATE/DELETE indevidos
foram recusados. Auditoria, histórico, conclusão sem aceite, rollback e
retencão de evidências foram revalidados. A perda legítima de FK em auditoria
preserva payload/timestamp; não autoriza adulteração arbitrária.

O histórico é protegido de usuários comuns por API/RLS/grants. Não foi criada
uma regra nova que impeça administradores SQL de administrá-lo. A proposta de
runtime nega UPDATE/DELETE em histórico, aceite e auditoria, e funcionou no fluxo
completo. Essa role existe apenas em transações de teste, não no Supabase.

**12. RLS**

Localmente, as nove tabelas protegidas têm RLS e clientes diretos não recebem
policies permissivas. Não foi utilizado FORCE RLS para quebrar o owner atual.
RLS não cobre TRUNCATE/REFERENCES, por isso as verificações de grants/operações
foram separadas. [RLS PostgreSQL](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

No Supabase, etapas_operacionais, historico_status_pedidos e alembic_version
continuam sem RLS. A comparação entre ambientes não significa alteração no real.

**13. Grants, defaults e runtime / SCRUM-103**

SELECT, INSERT, UPDATE, DELETE, TRUNCATE e ALTER indevidos foram tentados no
cluster descartável e negados para anon/authenticated. MAINTAIN também faz
parte da avaliação. Grants de tabela/coluna para PUBLIC são inspecionados.
alembic_version permanece acessível ao migrator autorizado, não à Data API.

O Supabase mantém defaults amplos e uma role SQL com ownership, BYPASSRLS,
CREATEROLE e CREATEDB. Não foi inventada uma credencial de runtime nem alterado
o schema gerenciado Storage. Retirar BYPASSRLS indiscriminadamente quebraria o
backend sem policies próprias; revogar defaults de outros creators pode afetar
outros consumidores. A separação runtime/migrator e a revisão por creator/schema
dependem de decisão operacional e autorização. A alternativa restrita foi
testada, mas não foi apresentada como configuração implantada.

**14. Functions**

As migrations existentes protegem `public.bloquear_alteracao_aceite_formal`,
`public.proteger_conclusao_pedido` e `public.proteger_auditoria_log`: SECURITY
INVOKER, referências qualificadas, search_path=pg_catalog, pg_temp e EXECUTE
retirado de clientes. Seis tentativas reais de EXECUTE pelas duas roles foram
negadas. No Supabase, as duas funções antigas continuam com proconfig nulo.

**15. Triggers**

Os três triggers de aceite/conclusão/auditoria permaneceram habilitados no
PostgreSQL local e após restore. Shadowing por tabela temporária não contornou
as proteções. A nova FK acrescenta triggers internos de integridade, sem
substituir os triggers de negócio. Owner/superuser continua uma fronteira de
confiança; triggers não impedem administração por uma role privilegiada.

**16. Storage e vínculo de anexos / SCRUM-87**

Todo anexo continua exigindo pedido e autor válidos. A FK composta agora impede
um par ocorrência/pedido inconsistente mesmo por SQL direto; tentativas de
INSERT, alteração do anexo e movimentação da ocorrência foram bloqueadas. Um
COMMIT inválido foi realmente recusado no PostgreSQL, com rollback comprovado.
Exclusão da ocorrência mantém o anexo e seu pedido, anulando ocorrencia_id;
exclusão do pedido aplica o CASCADE de metadados existente, sem excluir objetos.

Os testes cobrem arquivo inválido sem persistência, falha do Storage sem linha,
falha de FK após upload com compensação, falha de auditoria com rollback e
compensação, falha explícita da compensação e commit incerto sem exclusão cega.
Autorização horizontal, MIME/extensão e estrutura real do conteúdo continuam
validados. Esses uploads são doubles em memória; não foram uploads reais.

O bucket configurado foi auditado por leitura: privado, com RLS e sem policies
de cliente encontradas. O SDK conseguiu ler seus metadados. Limites de
tamanho/MIME no bucket continuam não configurados. Não houve envio, download
ou exclusão de objetos compartilhados.

**17. Órfãos: inventário e limite de apply**

O comando agora aceita `--dry-run --output <arquivo-local-novo>`. Gera recibo
com ID do objeto, hash do caminho, timestamps e fingerprint do inventário, sem
exportar nomes dos objetos ou connection strings. A saída é criada de modo
exclusivo, sem substituir evidência anterior. Duplicidade ambígua de objetos
aborta o inventário. Todos os achados continuam com delete=false.

O snapshot real foi completo e somente leitura: **0 referências, 0 objetos,
0 referências sem objeto, 0 objetos sem registro e 0 candidatos a órfão** no
bucket configurado. Isso vale para esse snapshot/bucket, não para todos os
buckets do projeto.

`--apply` é recusado antes de carregar configurações ou conectar. A remoção do
SDK instalado recebe caminhos e não oferece argumento condicional de versão;
um SELECT prévio não torna a exclusão atômica com uploads/metadados novos.
Sem coordenação de escritores e exclusão condicionada/quarentena aprovada,
habilitar a remoção não atenderia ao requisito de evitar corrida. Isso é uma
pendência de implementação/operacional, não apenas um botão aguardando liberação.
[API de remoção do SDK](https://supabase.com/docs/reference/python/storage-from-remove).

**18. Backend**

Psycopg2 e o contrato /auth/me foram preservados. ADMIN/TECNICO/CLIENTE recebem
a identidade/perfil corretos; sem token, inválido, inexistente ou inativo seguem
401. A autorização, as consultas administrativas, a persistência das etapas e
as seis provas de concorrência passaram. Não houve alteração de contrato HTTP,
services ou regras para acomodar testes.

**19. Frontend**

Nenhuma fonte Dart é rastreada por este backend; a única árvore disponível é
uma cópia não canônica. Foi duplicada em diretório temporário ignorado para
executar Flutter 3.47.2/Dart 3.13.2, sem modificar a original.

| Comando na cópia temporária | Resultado |
| --- | --- |
| pub get --offline | Código 0. |
| flutter analyze --no-pub | Código 1, 21 problemas. |
| flutter test --no-pub | Código 1, 9 testes passaram; 5 arquivos falharam ao carregar. |
| flutter build web --release --no-pub | Código 1, compilação falhou. |
| Provas isoladas de polling/modelo | 4 passaram. |

O erro raiz está em app_routes.dart:1: `import y'package:flutter/material.dart';`.
Não foi corrigido silenciosamente em uma cópia de origem desconhecida.
O teste isolado de polling passou; o aplicativo completo não está validado.

O código tem login, logout, Bearer, invalidação de sessão, cadastro/listagem,
proteção contra troca de usuário e paginação em blocos de 100. Progresso decimal
é aceito pelo parser. **Progresso null, permitido pelo backend, é rejeitado pela
cópia Flutter**, comprovado pela prova observacional. Não foi encontrado consumo
de /auth/me/provider de identidade; o login redireciona sempre a /home. Portanto,
redirecionamento ADMIN/TECNICO/CLIENTE, paginação >100 e fluxos completos não
estão certificados em runtime. Login/logout/JWT não foram declarados aprovados
no frontend só porque existem no código.

**20. Integração e SCRUM-105**

FastAPI/TestClient, JWT, services/repositories e PostgreSQL foram exercitados
com dados sintéticos reais. Não se alega E2E de navegador/aparelho ou Storage real.

O seed de homologação passou em dry-run com rollback e aplicação local
idempotente. Um pg_dump/pg_restore real restaurou em **outro banco novo**,
sem --clean, preservando ACLs. Dados, RLS, grants, policies e proteção das funções
coincidiram. O banco restaurado passou no Alembic check. Não foi restaurado
Supabase/Auth/Storage nem sobrescrito qualquer banco existente. O log separado
do seed contém o aviso não fatal conhecido de leitura da versão bcrypt pelo
Passlib; seed, idempotência e restore terminaram com sucesso.

**21. Supabase atual — somente leitura**

PostgreSQL 17.6, revisão **3c9e7a1b5d20**. Permanecem três tabelas sem RLS,
grants amplos de anon/authenticated, funções sem search_path fixo, ausência do
trigger novo da auditoria, runtime excessivo e defaults amplos. Bucket privado,
sem policies encontradas; agregados de integridade auditados sem divergências.
Nenhuma migration, DDL, DML, GRANT/REVOKE ou policy foi aplicada no real.

**22. Estado esperado após deploy autorizado**

Head d8f4a2c6e901, nove tabelas com RLS, grants/EXECUTE de clientes revogados,
funções e auditoria protegidas e vínculo composto de anexos validado. A cadeia
existente de segurança deve ser aplicada antes da revisão nova. Isso ainda não
foi feito. Defaults/runtime exigem revisão separada: não são corrigidos por
afirmação de que o head avançou. O bucket/objetos permaneceriam inalterados.

**23. Riscos**

A migration nova cria índice/constraints e valida dados existentes; janela,
locks, backup e preflight precisam de revisão antes do deploy. A FK diferida
valida no COMMIT; callers SQL não devem confundir flush com confirmação final.
Downgrade automático é recusado. Credenciais privilegiadas ainda permitem
administração fora das regras da API. Defaults podem expor futuros objetos.
O pipeline Flutter falha e o cleanup destrutivo não foi implementado. Restore
PostgreSQL isolado não equivale a um plano de desastre completo do Supabase.

**24. Matriz de tickets e pendências**

CONCLUÍDO abaixo significa aceite técnico comprovado no escopo informado do
ticket. Não significa produção atualizada. A coluna APLICADO distingue isso;
publicação/deploy desta rodada não foi executado. Não foram presumidos aceites
adicionais não fornecidos nem atualizados tickets externos.

| TICKET | IMPLEMENTADO | TESTADO | INTEGRADO | APLICADO | STATUS | PENDÊNCIA |
| --- | --- | --- | --- | --- | --- | --- |
| SCRUM-21 | Sim | Banco vazio, schema, driver e Alembic | Branch | Schema inicial real existente | CONCLUÍDO | Evolução de segurança tratada em 82/103; não confundir schema inicial com head atual. |
| SCRUM-39 | Sim na cópia | Polling isolado passa; app falha | Cópia não canônica | Não comprovado | BLOQUEADO | Origem canônica, correção do import e pipeline completo. |
| SCRUM-82 | Sim | Imutabilidade, rollback, shadowing | Branch/working tree | Não no Supabase | PARCIAL | Deploy autorizado e checagem pós-deploy. |
| SCRUM-87 | Vínculo/inventário sim; limpeza não | FK, preflight, compensação, recibos | Working tree | Local; real só leitura | PARCIAL | Deploy FK e protocolo seguro/autorizado de limpeza. |
| SCRUM-101 | Sim | Etapas persistidas e ciclo real | Branch | Tabela real existe; API não auditada em produção | CONCLUÍDO | Nenhuma no aceite técnico de repository; RLS em 103. |
| SCRUM-102 | Sim | Consultas e perfis no PostgreSQL | Branch | Local; deploy API não auditado | CONCLUÍDO | Nenhuma no aceite técnico de consultas do backend. |
| SCRUM-103 | Domínio sim; runtime/defaults parcial | Grants, RLS, MAINTAIN, EXECUTE e runtime | Branch/working tree | Não no Supabase | PARCIAL | Deploy, credencial runtime/migrator e defaults por creator/schema. |
| SCRUM-104 | Sim | Seis cenários reais de concorrência | Branch/working tree | Local | CONCLUÍDO | Ensaio técnico concluído; carga de produção não certificada. |
| SCRUM-105 | Sim | Seed e restore real com ACLs/check | Branch/working tree | Descartável, por desenho | CONCLUÍDO | Aceite PostgreSQL isolado concluído; não é DR de Auth/Storage. |

**25. Git final e preparação da entrega**

Diff check e cached diff check aprovados; sem marcadores de conflito. Scanner
de segredos sem correspondências em arquivos versionados; nenhum .env/bytecode
foi acrescentado. O .env preexistente permaneceu ignorado e não foi exportado.
O JSON registra o status final e hashes da entrega. Nada staged.
O contêiner novo foi parado (`exited`), com dados sintéticos locais retidos para
reprodução; nenhum contêiner anterior foi alterado. A checagem final confirmou
a FK composta validada/diferida e zero roles temporárias de runtime restantes.

Status final: 15 arquivos rastreados modificados e oito arquivos novos da
allowlist abaixo. Os sete itens locais restantes não pertencem à entrega:

```text
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/scrum82-103-validation-2026-11-02.json
?? docs/scrum82-103-validation-2026-11-02.md
?? frontend-Automatize-HML/
```

O status linha a linha completo está em `git_status_final` do JSON anexo.

**COMMIT RECOMENDADO — allowlist exata:**

```text
alembic/versions/d8f4a2c6e901_enforce_attachment_occurrence_order.py
app/domain/models/anexo.py
app/domain/models/ocorrencia.py
app/infrastructure/database/data_api_security.py
app/infrastructure/storage/reconciliation.py
docs/finalizacao-henrique-2026-11-02.json
docs/finalizacao-henrique-2026-11-02.md
docs/hml-validation-runbook.md
docs/security/data_api_hardening.sql
docs/security/persistence-hardening.md
scripts/audit_technical_state.py
scripts/reconcile_storage.py
scripts/validate_hml_restore.py
tests/integration/test_attachment_integrity.py
tests/integration/test_attachment_migration.py
tests/integration/test_concurrency_postgres.py
tests/integration/test_migration_upgrade.py
tests/integration/test_postgres_security.py
tests/integration/test_security_runtime_role.py
tests/test_data_api_security.py
tests/test_migrations_constraints.py
tests/test_reconcile_storage_cli.py
tests/test_restore_validation.py
```

**NÃO VERSIONAR nesta entrega:** `.env`, variantes com segredos, bytecode,
`.pytest_tmp*/`, três patches antigos, docs/evidence, frontend copiado e os dois
relatórios não rastreados SCRUM-82/103 da sessão anterior. Não foram apagados.
`.env.example` sanitizado já pertence ao projeto e não foi modificado.

**REVISAR MANUALMENTE:** semântica/locks da FK diferida, preflight legado,
recusa de downgrade, decisão de manter o SQL histórico apenas como documentação
e matriz de aceites por ticket. Os relatórios/evidências antigos podem ser
arquivados separadamente após revisão; não entram automaticamente neste commit.

**DEPENDE DE AUTORIZAÇÃO:** commit/push/atualização efetiva do PR; implantação
no Supabase; mudança de credenciais/defaults; qualquer limpeza real; alterações
no frontend canônico. Nenhuma dessas ações foi executada.

Mensagem sugerida:
`Consolida segurança e reforça integridade de anexos com validação final`

Atualização sugerida para o PR:

> Reforça no PostgreSQL o vínculo entre anexo, ocorrência e pedido, preservando
> CASCADE/SET NULL e abortando o upgrade se houver legado inconsistente.
> Consolida a auditoria/privilégios de SCRUM-82/103, acrescenta inventário
> explícito READ ONLY com recibos e valida restore com ACLs. Limpeza destrutiva
> continua bloqueada por falta de protocolo seguro; nenhum deploy no Supabase.
> Validação: 701 passed, 0 failed/errors/skipped, 168 PostgreSQL e 18 SCRUM-71.
> A cópia Flutter falha em analyze/test/build e permanece fora desta entrega.

Não foi publicado comentário ou alteração no PR. O trabalho termina para revisão
e autorização do usuário.
