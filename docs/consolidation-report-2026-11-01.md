# Consolidação do Automatize para revisão — 01/11/2026

Este relatório substitui, para o estado atual do código, as pendências de escolha
de regra/backend registradas na auditoria de 31/10. A SCRUM-71 é oficial e foi
implementada na raiz, preservando as correções locais e o PR #12. Documentos
datados anteriores permanecem como histórico da auditoria, não como regra atual.

## A. VERSÕES ANALISADAS

| Referência | Branch/origem | Commit exato | Estado |
| --- | --- | --- | --- |
| Raiz | Henrique-Silva | `1b6203b4b2e6fa90e5f6bf0ac82eb68e795b8ea9` | Working tree já continha correções não commitadas; preservadas e consolidadas |
| HML remota atual | origin/HML | `f4f89e787cde2333f4b99696e7c9d15a61fdfabb` | Atualizada por fetch explícito e analisada sem checkout/merge |
| PR #12 | Luis-Santini → HML | head `fd5a1fe84cb29fc2ee86ee5ffa77ec3743f1df02`; merge `f4f89e787cde2333f4b99696e7c9d15a61fdfabb` | Integrado |
| Cópia backend-Automatize-HML | Sem Git próprio | Correspondência de conteúdo com HML acima | 107 arquivos relevantes coincidem, normalizando apenas CRLF/LF |

**PR #12 presente na HML: SIM.**
[PR e regra integrados](https://github.com/ALISSINHO-1/backend-Automatize/pull/12).

Executados antes de editar: git status, branch, log -5 e fetch origin. O refspec
do clone só buscava Henrique-Silva; portanto o fetch padrão não atualizava HML.
Foi executado adicionalmente:

```text
git fetch origin refs/heads/HML:refs/remotes/origin/HML
```

HML passou de `e51b27f2da87b1d32539f664e44af32c78636bf1` para o SHA acima.
Nenhuma branch local foi trocada. Comparar o HEAD de Henrique com essa HML mostra
seis arquivos: três de implementação e três de testes. O PR #11 já levou as
correções commitadas de Henrique à HML; o PR #12 acrescentou a regra de etapas e
a linha do tempo. As alterações não commitadas da auditoria foram reconciliadas
com esses deltas, sem substituir versões inteiras.

Evidência arquivo a arquivo, hashes e estado inicial:
[versions-and-comparison.json](evidence/consolidation-2026-11-01/versions-and-comparison.json).
Os 621 testes correspondem ao working tree consolidado, não somente ao HEAD.

## B. SCRUM-71

| Verificação | Resultado |
| --- | --- |
| Regra oficial implementada | SIM |
| Sem etapas bloqueia HOMOLOGACAO | SIM, a partir de PLANEAMENTO e EXECUCAO |
| Uma etapa pendente bloqueia | SIM |
| Várias etapas com alguma pendente bloqueiam | SIM |
| Ao menos uma etapa e todas concluídas permitem | SIM, a partir de EXECUCAO e com equipe autorizada |
| Recusa desfaz alterações/status/histórico/auditoria | SIM |

Matriz explícita: **18 passed / 0 failed**, em PostgreSQL real, exercitando
DemandService, PedidoService e API com JWT. Inclui seis casos A, três B, três C
e seis D, considerando as entradas e quantidades distintas. As regras puras e
os três testes de regressão preservados do PR #12 também passam na suíte completa.

`ciclo_vida.validar_transicao` recebe total_etapas e pendências; o validador
central lê a contagem da lista persistida. PedidoService.atualizar continua
delegando essa validação central, preservando ator ativo, escopo, lock,
populate_existing, histórico e auditoria. validar_e_transitar recebeu os
parâmetros opcionais já introduzidos pelo PR #12. Não há contagem confiada ao body.

Helpers de testes válidos agora cadastram e concluem uma etapa antes de
homologar. A regra não foi afrouxada para satisfazer fixtures antigas. Nenhuma
decisão de negócio sobre homologação sem etapas permanece aberta nesta entrega.
Comparação por AST, excluindo apenas docstrings, confirmou igualdade com a HML
para validar_transicao, validar_e_transitar e listar_estados:
[evidência](evidence/consolidation-2026-11-01/official-pr12-function-comparison.json).

## C. 31 FALHAS

### Reprodução identificável

- Branch de origem: HML, exportada por git archive no SHA exato
  `f4f89e787cde2333f4b99696e7c9d15a61fdfabb`.
- Branch controladora do workspace: Henrique-Silva, HEAD
  `1b6203b4b2e6fa90e5f6bf0ac82eb68e795b8ea9`. O snapshot exportado não tem .git;
  ele não é um checkout da branch local Henrique nem foi alterado na reprodução.
- Python: **3.14.7, AMD64**, da `.venv/Scripts/python.exe` deste workspace.
- Prefixo: `.venv`; base Python em AppData/Local/Python/pythoncore-3.14-64;
  ambiente criado com acesso aos pacotes do Python base.
- Bibliotecas: FastAPI 0.141.1, SQLAlchemy 2.0.52, Alembic 1.20.0,
  psycopg2-binary 2.9.13, pytest 9.1.1.
- PostgreSQL: **17.11**, container descartável próprio, loopback porta 55440,
  isolamento READ COMMITTED. Bancos de reprodução distintos e vazios.
- TEST_DATABASE_URL aponta somente para banco local com nome contendo test.
  DATABASE_URL não é sobrescrita globalmente para pytest; a fixture a troca
  temporariamente para Alembic. Storage é fake. Nenhuma credencial é exportada.

Comando da reprodução completa, com JUnit apenas como coleta de evidência:

```text
python -m pytest tests/integration -q --tb=short --junitxml=<evidência>/hml-all.xml
```

CWD: `.pytest_tmp_consolidation/hml-exact`. Banco: `automatize_hml_repro_test`.
Resultado: **25 passed / 31 failed / 0 skipped / 2 warnings**.
A execução da cópia local original, em `automatize_copy_repro_test`, confirmou
o mesmo resultado. A equivalência de fontes com o commit foi verificada antes.

Primeiro teste que falha:
`tests/integration/test_demand_service_db.py::test_conclusao_nao_pode_ser_feita_por_alteracao_de_status`.

Comando da primeira falha completa:

```text
python -m pytest tests/integration -q -x --full-trace --tb=long --junitxml=<evidência>/hml-first.xml
```

CWD igual; banco separado `automatize_hml_first_test`.
Resultado: **12 passed / 1 failed / 2 warnings** antes de interromper no primeiro erro.

**Traceback completo, sem omissão de frames:**
[hml-first.log](evidence/consolidation-2026-11-01/hml-first.log).
[Comando, Python, venv, CWD e configuração segura](evidence/consolidation-2026-11-01/hml-first-environment.json).

### CAUSA RAIZ

O helper tenta registrar a etapa exigida para homologação. DemandService
adicionar_etapa envia created_at para EtapaOperacionalRepository.create.
BaseRepository.create rejeita timestamps internos:

```text
test_conclusao_nao_pode_ser_feita_por_alteracao_de_status
  → _em_homologacao
  → DemandService.adicionar_etapa (HML: linha 339)
  → BaseRepository.create (linha 80)
  → ValueError: Não é permitido definir campos internos na criação.
```

As 31 falhas chegam ao mesmo guard. A proteção de campos internos é válida e
foi preservada; a raiz já havia retirado esse envio indevido e usa o default do
banco. O conflito é entre um caller antigo e uma proteção posterior, não a regra
oficial de homologação. Blame identifica a proteção em `3dbec3f8` e o envio de
timestamp em `f432fcf9`; ambos estão no histórico atual da HML.

### FALHAS EM CASCATA

O primeiro teste é a manifestação representativa da causa raiz. As outras 30
falhas também dependem da criação de etapas: testes de aceite, rejeição,
imutabilidade, linha do tempo, evidência e endpoints não chegam às respectivas
assertions de negócio. Trata-se de uma dependência funcional comum, **não** de
estado vazando sequencialmente de um teste para o seguinte.

Lista nominal e classificação das 31:
[failure-classification.json](evidence/consolidation-2026-11-01/failure-classification.json).
Não foram feitas 31 correções pontuais para esconder esses resultados.

### FALHAS INDEPENDENTES

Uma cópia diagnóstica recebeu **somente** a retirada de created_at, sem mudar
testes ou SCRUM-71: **55 passed / 1 failed / 2 warnings**.
[Patch único](evidence/consolidation-2026-11-01/diagnostic-single-fix.patch) e
[resultado](evidence/consolidation-2026-11-01/hml-diagnostic.log).

A falha remanescente, `test_progresso_persistido_acompanha_etapas`, pressupõe
ordem de inserção. CURRENT_TIMESTAMP é constante na transação externa da fixture;
o repository ordena por created_at e UUID, não por número escrito na descrição.
O teste corrigido da raiz já verifica o conjunto de etapas e a ordenação definida
por `(created_at, id)`. Essa correção foi preservada.

Conclusão: os 31 resultados não representam 31 defeitos independentes nem
justificam descartar a HML. A causa de criação de etapas e a suposição frágil de
ordenação foram tratadas sem enfraquecer proteção ou SCRUM-71.

## D. BACKEND

Suíte completa final: **621 passed / 0 failed / 0 skipped / 2 warnings**.
Comando: `python -m pytest tests -q --tb=short`, com coleta JUnit adicional.
Banco: `automatize_consolidation_test`, PostgreSQL 17.11 descartável.
[Log completo](evidence/consolidation-2026-11-01/root-all.log).

Foi executado também um grupo crítico separado após a suíte completa, abrangendo
integração PostgreSQL, services, repositories, autenticação/autorização, anexos,
auditoria, histórico, concorrência, migrations e segurança.
Resultado separado final: **492 passed / 0 failed / 0 skipped / 2 warnings**.
[Log crítico](evidence/consolidation-2026-11-01/root-critical.log) e
[resumo verificável](evidence/consolidation-2026-11-01/test-summary.json).

Os dois warnings são depreciações de FastAPI/Starlette/AnyIO relacionadas a httpx
e BlockingPortal. Não foram ocultados nem provocaram atualização ampla de pacotes.

## E. FRONTEND

- `flutter analyze --no-pub`: **sem problemas**, exit 0.
- `flutter test --no-pub`: **31 passed**, exit 0.
- Nenhuma fonte Dart foi modificada nesta consolidação; isso foi conferido com
  o snapshot inicial. Não houve mudança visual.
- SCRUM-39: polling 30 s, mudança visível sem reinício, retorno à tela,
  preservação de Bearer/JWT, suspensão com rota/app inativo, deduplicação,
  recuperação de erro HTTP e cancelamento no dispose continuam testados.

[Resultados e comandos](evidence/consolidation-2026-11-01/flutter-results.json).
Integração esperada: login, listagem e cadastro CLIENTE mantêm contrato
Flutter → FastAPI → PostgreSQL. Homologação/anexos do Flutter ainda são
demonstrativos; o método de linha do tempo existe no backend consolidado, mas
não está exposto por rota nem consumido pela tela. Não foi alegado E2E de aparelho
ou navegador com escrita no Storage real.

## F. ALEMBIC

| Ambiente | Head/current | Check |
| --- | --- | --- |
| Código consolidado | Uma head: `b6e1c8a4d230` | Cadeia linear |
| HML commit f4f89e7 | Head `7b2d4e6f8a10` | Sem migrations novas no PR #12 |
| PostgreSQL descartável | Current `b6e1c8a4d230` | No new upgrade operations detected |
| Supabase compartilhado | Current `3c9e7a1b5d20` | Target database is not up to date, em READ ONLY |

**Banco compartilhado está atrás da head: SIM.** O check desse banco não foi
apresentado como aprovado. Não houve tentativa de upgrade nele.

Executados heads, history, current, upgrade head e check **somente no PostgreSQL
descartável** quando havia escrita. Current/check compartilhados receberam
`default_transaction_read_only=on` explícito e timeout; saída filtrada e sem URL.
Os testes também criam banco vazio até head e banco na revisão 3c9 até head,
preservando dados/grants de teste e validando constraints, FKs, triggers,
funções, RLS e privilégios reais. Nenhum arquivo de migration foi alterado nesta
consolidação; as duas migrations de segurança já preparadas foram preservadas.
Não foram executados DROP, TRUNCATE, downgrade ou stamp.

[Comandos locais](evidence/consolidation-2026-11-01/alembic-local.log) e
[resultados compartilhados somente leitura](evidence/consolidation-2026-11-01/alembic-shared-readonly.json).

## G. SEGURANÇA

| ALERTA/OBJETO | Corrigido no código? | Migration criada? | Teste aprovado? | Aplicado no Supabase? |
| --- | --- | --- | --- | --- |
| public.etapas_operacionais / RLS | SIM | SIM: 7b2 + complemento 9d4 | SIM, PostgreSQL real | NÃO |
| public.historico_status_pedidos / RLS | SIM | SIM: 7b2 + complemento 9d4 | SIM | NÃO |
| public.alembic_version / exposição | SIM | SIM: 7b2 + REVOKEs 9d4, sem policy permissiva | SIM, inclusive Alembic | NÃO |
| GRANT/REVOKE anon/authenticated/PUBLIC, tabelas e colunas | SIM | SIM: 9d4f2a6c8e11 | SIM, com grants herdados/efetivos avaliados | NÃO |
| bloquear_alteracao_aceite_formal / search_path e EXECUTE | SIM | SIM: 9d4f2a6c8e11 | SIM, UPDATE/DELETE negados | NÃO |
| proteger_conclusao_pedido / search_path e EXECUTE | SIM | SIM: 9d4f2a6c8e11 | SIM, shadowing temporário não permite concluir | NÃO |
| Auditoria append-only, preservando FK SET NULL | SIM | SIM: b6e1c8a4d230 | SIM | NÃO |

Status dos itens pendentes no ambiente: **CORRIGIDO EM CÓDIGO — IMPLANTAÇÃO
PENDENTE**. As migrations já existiam como trabalho local antes desta etapa;
foram preservadas e retestadas. Não é resolução em produção.

A inspeção READ ONLY confirmou as três tabelas ainda sem RLS, proconfig nulo nas
duas funções e EXECUTE efetivo para anon/authenticated. A role do backend tem
BYPASSRLS, CREATEROLE e CREATEDB. Nenhuma role, policy ou bucket foi alterado.
Não foi usado FORCE RLS nem criada policy permissiva para eliminar um alerta.

[Catálogo atual sem dados de aplicação/credenciais](evidence/consolidation-2026-11-01/shared-catalog-readonly.json).

## H. SCRUM-87

- **Vínculos:** anexo → pedido, ocorrência e usuário preservados. O repository
  valida ocorrência do mesmo pedido e mantém seu lock durante upload/persistência.
- **FKs:** cenários de pedido e usuário inexistentes exercitam FK real PostgreSQL
  (SQLSTATE 23503), com compensação do upload já realizado.
- **Compensação:** Storage funciona/DB falha remove o arquivo do fake; falha do
  Storage não deixa metadata; falha de refresh após commit confirmado preserva
  metadata e arquivo. Quatro testes novos passam em PostgreSQL real, Storage fake.
- **Inventário:** READ ONLY/REPEATABLE READ, agora bidirecional. Reporta objetos
  sem registro e registros sem objeto no bucket configurado, por hash do caminho.
  Snapshot incompleto não produz conclusões falsas de ausência. Não baixa conteúdo.
- **Órfãos encontrados no snapshot compartilhado:** zero objetos e zero
  referências no bucket configurado; portanto zero candidatos e zero referências
  sem objeto no catálogo. Esse resultado não certifica bytes físicos fora do
  catálogo nem outros buckets.
- **Limpeza executada: NÃO.** Não há opção apply/delete no inventário.

**Classificação final: PARCIAL.** Inventário dry-run não equivale a execução
controlada de limpeza nem a uma transação distribuída DB/Storage.
[Inventário somente leitura](evidence/consolidation-2026-11-01/storage-inventory-dry-run.json).

## I. TICKETS

Classificação para implementação/evidência local revisável, sem movimentação Jira:

| Ticket | Situação | Evidência curta |
| --- | --- | --- |
| SCRUM-21 | CONCLUÍDO | Conexão real em leitura; schema/FKs e migrations testados em PostgreSQL isolado |
| SCRUM-39 | CONCLUÍDO | Analyze e 31 testes Flutter, polling e ciclo de vida preservados |
| SCRUM-71 | CONCLUÍDO | Regra oficial, matriz A/B/C/D e rollback: 18 casos PostgreSQL aprovados |
| SCRUM-82 | PARCIAL | Imutabilidade/funções protegidas e testadas no código; implantação pendente |
| SCRUM-87 | PARCIAL | Vínculos/compensação testados; inventário exclusivamente dry-run |
| SCRUM-101 | CONCLUÍDO | Etapas persistem sem violar campos internos; progresso, transações e FKs testados |
| SCRUM-102 | CONCLUÍDO | Endpoints/perfis/escopo por pedidos; acesso horizontal negado |
| SCRUM-103 | PARCIAL | RLS/grants/EXECUTE preparados e testados; banco real ainda desatualizado |
| SCRUM-104 | CONCLUÍDO | Concorrência de etapa, responsável, aceite e estado; stale read e rollback testados |
| SCRUM-105 | CONCLUÍDO | Seed sintético idempotente; restore em banco novo preservou linhas, RLS, grants e funções |

SCRUM-105 foi revalidado nesta execução: 3 usuários, 2 pedidos, 1 ocorrência,
2 etapas, 1 aceite, 9 logs, 3 eventos de estado e zero anexos inventados.
pg_dump/pg_restore usaram banco novo, sem clean/DROP/TRUNCATE, preservando ACLs;
hashes e catálogos de acesso coincidiram. Storage/Auth gerenciado não integram
esse ensaio PostgreSQL. [Evidência](evidence/consolidation-2026-11-01/hml-seed-restore.json).

## J. ALTERAÇÕES REALIZADAS

Diferença desta etapa em relação ao inventário inicial, sem atribuir trabalho
anterior a esta consolidação:

| Arquivo | Motivo |
| --- | --- |
| app/domain/regras/ciclo_vida.py | Total de etapas e bloqueio sem etapas do PR #12; mantém demais transições |
| app/services/demand_service.py | Passa contagem real ao validador compartilhado e preserva listar_estados da HML |
| app/services/pedido_service.py | Helper legado recebe os parâmetros do PR #12; atualizar mantém segurança/lock/delegação da raiz |
| app/infrastructure/storage/reconciliation.py | Acrescenta referências sem objeto e contagens; ausência depende de snapshot completo |
| scripts/reconcile_storage.py | Usa inventário bidirecional existente, ainda somente leitura |
| tests/test_regras_ciclo_vida.py | Remove expectativa antiga de homologar sem etapas; cobre regra oficial e helper legado |
| tests/integration/test_demand_service_db.py | Fixture válida com etapa e três regressões já integradas no PR #12 |
| tests/integration/test_demandas_acoes_api.py | Helper de homologação prepara/conclui etapa e verifica cada resposta |
| tests/integration/test_concurrency_postgres.py | Setups concorrentes de homologação cumprem SCRUM-71, mantendo assertions de corrida |
| tests/integration/test_scrum71_homologacao.py | Novo: matriz A/B/C/D pelos dois services e API, incluindo rollback persistido |
| tests/integration/test_attachment_storage_transactions.py | Novo: FK real, compensação e falha posterior a commit confirmado |
| tests/test_storage_reconciliation.py | Casos de referências sem objeto e inventário incompleto sem falso positivo |
| docs/audit-integration-map.md | Regra/backend já reconciliados; método de histórico preservado e limites HTTP explícitos |
| docs/hml-validation-runbook.md | Fixtures SCRUM-71, inventário bidirecional e validação de restore com ACLs |
| docs/consolidation-report-2026-11-01.md | Este relatório A–L e links às evidências |
| docs/consolidation-session.patch | Patch apenas das alterações de código desta etapa |
| docs/consolidation-vs-HML.patch | Patch completo do backend contra a HML atual, incluindo trabalho anterior preservado |
| docs/evidence/consolidation-2026-11-01/* | Logs/JUnit, ambiente sem credenciais, comparação por arquivo e evidências de banco |

Nenhum arquivo de model, repository, migration, autenticação ou endpoint foi
substituído pela versão de outro lado. O guard de campos internos, parsers de
anexos, TLS, configuração Storage injetada, autorização administrativa, auditoria,
transações e proteção de concorrência já preparados na raiz foram mantidos.
Nenhuma fonte Flutter foi alterada.

[Manifesto de alterações de código desta sessão](evidence/consolidation-2026-11-01/session-code-changes.json).
O patch completo contra HML inclui arquivos novos necessários já existentes no
working tree; os arquivos anteriores não foram apagados, staged ou commitados.
`git apply --check` contra o snapshot HML, `git diff --check` e a busca de conflitos
passaram. Não há arquivos unmerged. [Verificações finais](evidence/consolidation-2026-11-01/final-checks.json).

## K. PENDÊNCIAS PARA PRODUÇÃO

Somente lacunas comprovadas por código ou leitura do ambiente:

1. O Supabase compartilhado está atrás da head e mantém as três RLS ausentes,
   grants amplos e search_path/EXECUTE das funções sem o hardening preparado.
2. A role PostgreSQL usada pelo runtime tem poderes administrativos excessivos;
   CREATEROLE/CREATEDB e BYPASSRLS foram confirmados no catálogo. Separação de
   runtime/migrator exige desenho e implantação próprios, não executados aqui.
3. O Flutter recebido ainda não envia aceite/rejeição/anexos reais e não consome
   a linha do tempo. A integração de etapas necessária antes de homologar não
   está completa na interface. O contrato atual de histórico da API é auditoria,
   distinto do model de linha do tempo; o método do PR #12 ainda não tem rota.
4. A reconciliação de anexos é dry-run. Não existe execução controlada e auditável
   de limpeza. Zero candidatos no snapshot atual não elimina a lacuna operacional.

Não se afirma que existem órfãos reais, dados corrompidos ou 31 defeitos
independentes. Nenhuma conclusão sobre os demais alertas não fornecidos do
Advisor foi inventada. Não houve teste de escrita em Storage compartilhado.

## L. RECOMENDAÇÃO DE INTEGRAÇÃO

**Pronta tecnicamente para revisão/PR do backend consolidado: SIM**, após revisão
dos patches e autorização para commit. A SCRUM-71 não é mais bloqueio ou decisão
pendente. Não há falha de teste conhecida na raiz consolidada.

**O que bloqueia abrir o PR agora:** falta de autorização para commit/publicação;
nenhum commit ou PR foi criado. O working tree contém trabalho anterior e uma
cópia Flutter não versionada, portanto a seleção de arquivos deve seguir o patch
revisado do backend. Não houve merge, rebase, push ou aprovação de PR.

**O que bloqueia produção:** as quatro lacunas comprovadas da seção K. Migrations
preparadas não significam implantação aprovada. Atualizar o ambiente compartilhado
é etapa posterior, com plano de rollout, autorização e validação próprios.

O container e todos os bancos usados para escrita são descartáveis e contêm
somente dados sintéticos. Evidências foram registradas antes de seu encerramento.
Nenhum usuário/senha real, objeto do Storage ou dado do Supabase foi modificado.
