# SCRUM-87 e preparação final do Supabase

Rodada: 2026-11-05. Base publicada:
`a46285060c6211c1f7dc41d24ae33d0e6e03503a`, branch `Henrique-Silva`.
Relatório e evidências desta execução: este arquivo e
[scrum87-supabase-preparation.json](scrum87-supabase-preparation.json).
Os relatórios anteriores permanecem históricos, sem reutilizar suas contagens
como resultados novos.

## Diagnóstico antes das alterações

HEAD e origin/Henrique-Silva coincidiam em a462850, sem alterações rastreadas e
sem staged. Existiam apenas patches, docs/evidence e a cópia Flutter não rastreados;
foram preservados por hash. Foram lidos reconciliation, cleanup_review, adapter,
service/repository de anexos, endpoints/fluxos de exclusão, SDK instalado, testes,
runbook e schema_preflight antes de alterar código.

Lacuna encontrada: o inventário inicial marcava complete_snapshot=true após
consultas que poderiam ser filtradas por RLS ou direcionadas a bucket inexistente.
A segunda verificação já tinha guardas de visibilidade, mas a captura inicial
ainda não. Isso poderia produzir candidatos ou ausências incorretos, embora
apply já fosse incondicionalmente recusado.

## O que foi resolvido localmente

- `reconcile_storage` agora exige visibilidade completa de anexos/pedidos e dos
  catálogos storage.objects/storage.buckets. Falta de SELECT, RLS efetivamente
  filtrando linhas, bucket ausente ou público abortam antes de emitir recibo.
  Nenhum grant, policy ou dado é alterado para obter essa visibilidade.
- Novos testes PostgreSQL cobrem essas recusas, com catálogo Storage simulado
  em banco próprio. Os testes do CLI continuam comprovando apply recusado antes
  de ler configuração/conectar e recibo sem paths/credenciais.
- O adapter real foi exercitado sobre SDK simulado em outra thread, com commits
  PostgreSQL reais: upload antes do registro, referência posterior, timeout de
  ACK, compensação e falha da compensação. Caminho reutilizado mas referenciado
  continua protegido. Não foram usados objetos ou credenciais compartilhados.
- Foram preparadas e executadas localmente as consultas de
  [supabase-readonly-preflight.sql](security/supabase-readonly-preflight.sql).
  Elas auditam schema/constraints/revisão, RLS, grants de tabela/coluna/PUBLIC,
  defaults por criador, MAINTAIN, roles/memberships, funções/EXECUTE, triggers,
  policies e metadados do Storage em transação somente leitura.
- O runbook foi atualizado para o estado remoto atual, backups com ACLs, seleção
  de artefato, checklist de aprovação/interrupção e recuperação sem downgrade
  automático. Foi criado um procedimento separado para os bytes do Storage.

Nenhum model, migration, regra de negócio, service ou contrato da API foi
alterado. Os locks por pedido, validação estrutural/MIME, compensação existente,
commit incerto, imutabilidade e permissões anteriores foram preservados.

## Operações e limite técnico da SCRUM-87

O mapa completo dos escritores está em
[storage-backup-recovery-runbook.md](storage-backup-recovery-runbook.md): upload
com UUID/upsert=false; compensações do adapter/service; registro de anexo e
auditoria; commits/rollback/refresh; cascatas de metadados; SQL/restore e possíveis
clientes externos/Dashboard/S3. FOR UPDATE do pedido não é barreira global do
bucket. Não foram encontrados consumidores de move/copy/update/empty/delete_bucket
nos caminhos de produção versionados examinados.

O storage3 instalado, **2.33.0**, implementa remove(paths) com apenas prefixes no
payload. A [referência Python](https://supabase.com/docs/reference/python/storage-from-remove)
não fornece contrato de remoção individual por geração. A
[compatibilidade S3](https://supabase.com/docs/guides/storage/s3/compatibility)
informa ausência de versionamento e não comprova compare-and-delete de geração;
HEAD/GET condicionais não fecham essa corrida. Não foi inferida garantia a partir
de ETag, timestamp ou ID de catálogo, nem se declarou impossibilidade de versões
futuras do provedor.

**Não foi implementado limpador destrutivo.** Apply continua recusado, o ensaio
sempre retorna delete=false, e não há protocolo global de escritores nem ledger
durável de limpeza implementados. Aprovação humana não substitui essas garantias.

Alternativa imediata: quarentena **lógica**, um recibo restrito e revisado sem
alterar o objeto original. Uma cópia externa de backup pode preservar os bytes
sob janela coordenada. Quarentena física/move ou copy seguido de delete têm a
mesma corrida de substituição e permanecem desabilitados. Serviço controlado
exigiria identidade/fencing/exclusividade comprovados no servidor, todos os
escritores participantes, intenção durável e recuperação ensaiada.

## Resultado dos testes desta rodada

| Execução real | Passed | Failed | Errors | Skipped | Warnings | PostgreSQL |
| --- | --- | --- | --- | --- | --- | --- |
| Específicos, antes do ajuste de isolamento | 47 | 0 | 0 | 0 | 0 | 42 |
| Suíte completa final em banco novo | **763** | **0** | **0** | **0** | **1** | **219** |

Comando principal: `python -m pytest tests -q`, com TEST_DATABASE_URL local,
logs/JUnit próprios e SDK Storage simulado. Os 763 são os 748 casos da base
publicada mais 15 novos: 8 de visibilidade/inventário, 3 de upload concorrente e
4 da auditoria SQL. Nenhum teste PostgreSQL foi ignorado. O warning é a
depreciação Starlette/httpx no TestClient, sem falha funcional.

Subconjuntos, já incluídos na suíte e sem somar execuções sobrepostas:

- SCRUM-71: **18 PG**, sem etapas/uma pendente/múltiplas com pendência bloqueadas;
  ao menos uma e todas concluídas permitidas. Regra não alterada.
- Revisão de órfãos existente: **27 PG**, incluindo IDs/versões/paths trocados,
  referências concorrentes, timeouts, permissões/RLS e shadowing de catálogo.
- Segurança PostgreSQL: **34**, mais **16** de runtime restrito.
- Pré-validação estrutural: **9 PG**, incluindo baseline reescrito com mesmo ID,
  revisão desconhecida, drift de função/coluna e trigger desabilitada.

A primeira suíte completa teve **6 failed / 757 passed**: duas execuções dos
novos testes concorrentes tinham deixado anexos sintéticos no banco raiz usado
depois pela suíte. As falhas eram assertions existentes de contagem global.
Não foram removidas ou relaxadas. Os novos cenários passaram a usar bancos
próprios, e a execução final usou outro banco raiz novo. O banco da tentativa
anterior foi preservado para diagnóstico; nenhum dado real foi apagado.

Ambiente: Python 3.14.7, SQLAlchemy 2.1.6, Alembic 1.20.1,
psycopg2-binary 2.9.13 e PostgreSQL **17.11** em Docker, somente loopback.
Venv isolada existente reutilizada, sem alegação de nova instalação pip.
Nenhuma dependência foi acrescentada e nenhuma URL/credencial foi exportada.

## Alembic e ensaio PostgreSQL

Uma head local: **d8f4a2c6e901**. Current igual à head;
`No new upgrade operations detected`. Heads/current/check/history foram executados.
Os testes de migrations do zero e upgrade de banco existente passaram.
Nenhuma migration foi criada/alterada.

Novo dump/restore real em bancos sintéticos separados: 3 usuários, 2 pedidos,
1 ocorrência, 2 etapas, 1 aceite, 9 logs, 1 anexo, 3 históricos e 1 versão Alembic.
Contagens/fingerprints e segurança iguais; owners/ACLs/defaults preservados,
3 triggers ativas, revisão d8 e check limpo no destino. Não se usou clean,
no-owner ou no-privileges. Dumps e bancos locais foram preservados.

Limites: roles globais reutilizadas no mesmo cluster, não recriadas em outro;
bytes do Storage não foram restaurados. Isso não comprova backup/recuperação
do projeto compartilhado. O roteiro separado explica snapshot coordenado,
destino independente criptografado, manifesto/SHA-256, recuperação em projeto
privado novo, idempotência e interrupção diante de colisão/estado incerto.

## Situação remota e compatibilidade

Fetch e consulta ao GitHub confirmaram mudanças externas nesta rodada:

| Referência | Commit / head Alembic |
| --- | --- |
| Henrique-Silva | a462850 / d8f4a2c6e901 |
| main | e7a5d48 / f9a2d4c6b803 |
| HML | 2e26b03 / f9a2d4c6b803 |
| Luís | e6f197f / f9a2d4c6b803 |
| PR15 snapshot | df6f3b4 / f9a2d4c6b803 |

PR14 merged com head **3ef5080**; PR15 merged em Luís; PR13 merged em HML,
depois integrada à main pelo PR16. O complemento a462850 **não** está no histórico
da main. Esses merges foram realizados por terceiros, não nesta sessão.

As oito migrations locais compartilhadas têm conteúdo idêntico nas refs atuais.
A cadeia adicional é linear `d8 -> e3b7c1d9f402 -> f9a2d4c6b803`, sem duplicação
de revisão. A inicial com ID fbfba8e84540 já tem DDL na main atual, mas era vazia
na main histórica 2c02343. O catálogo de instalações antigas ainda exige revisão;
rótulo igual não prova equivalência e stamp não foi usado.

Não basta copiar apenas o patch de reconcile_storage para main: ele depende dos
helpers do complemento a462850, ainda ausentes nessa linha remota. Integração
futura deve preservar os modelos/regras do Luís e endpoints do Alisson e repetir
os testes, sem trazer snapshots antigos sobre seus arquivos. Não foi testado um
artefato mesclado nesta sessão, nem realizado merge/rebase/cherry-pick.

O bloqueio adicional por ocorrência aberta já está na main via SCRUM-98; não foi
introduzido na branch local nesta rodada. Na implantação, escolher artefato e
revisão fixados: o schema_preflight desta branch d8 recusa f9 desconhecida.
Não copiar migrations isoladas para contornar essa recusa.

## Concluído, bloqueado e dependente de aprovação

| Item | Situação |
| --- | --- |
| Diagnóstico de escritores/SDK e correção de completude | implementados e testados localmente |
| Consultas read-only e gates/runbook | preparados e testados em catálogo simulado local |
| PostgreSQL, migrations, ACLs/triggers e restore sintético | aprovados localmente |
| Backup/recuperação dos bytes e alternativa de quarentena | procedimento preparado; execução real não feita |
| Exclusão condicional/global fencing/ledger durável | tecnicamente não comprovados/implementados; SCRUM-87 **PARCIAL** |
| Integração do complemento a462850 e patch atual | depende de revisão/autorização e nova validação do artefato integrado |
| Janela, RPO/RTO, credenciais/roles, backup real e deploy | dependem de autorização e operação |
| Supabase protegido/aplicado/verificado | **não declarado**; nenhum acesso ou alteração compartilhada nesta rodada |

O estado real do Supabase não foi consultado; o registro histórico em 3c9 de
2026-11-02 não foi tratado como informação atual. Não houve aplicação de
migration, grant/revoke/policy, remoção de metadado ou exclusão de objeto real.

## Qualidade e entrega

Git diff/check e cached/check: exit 0, somente avisos de conversão LF/CRLF.
Arquivos novos também foram conferidos quanto a whitespace. Nenhum marcador
de conflito, segredo correspondente ao .env local, JWT literal, .env real ou
bytecode nos arquivos rastreados/da entrega. Os 112 arquivos não rastreados
preexistentes continuam íntegros por hash. Nada staged; branch/HEAD preservados.

Estado Git final, incluindo arquivos locais preservados fora da entrega:

```text
 M docs/storage-orphan-cleanup-strategy.md
 M docs/supabase-deployment-runbook.md
 M scripts/reconcile_storage.py
 M tests/test_reconcile_storage_cli.py
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/scrum87-supabase-preparation.json
?? docs/scrum87-supabase-preparation.md
?? docs/security/supabase-readonly-preflight.sql
?? docs/storage-backup-recovery-runbook.md
?? frontend-Automatize-HML/
?? tests/integration/test_storage_inventory_visibility.py
?? tests/integration/test_supabase_readonly_queries.py
?? tests/integration/test_upload_reconciliation_races.py
```

Lista exata para um possível commit, após aprovação:

```text
scripts/reconcile_storage.py
tests/test_reconcile_storage_cli.py
tests/integration/test_storage_inventory_visibility.py
tests/integration/test_upload_reconciliation_races.py
tests/integration/test_supabase_readonly_queries.py
docs/security/supabase-readonly-preflight.sql
docs/storage-backup-recovery-runbook.md
docs/storage-orphan-cleanup-strategy.md
docs/supabase-deployment-runbook.md
docs/scrum87-supabase-preparation.md
docs/scrum87-supabase-preparation.json
```

Não versionar patches, docs/evidence preexistente, cópia Flutter, .env, venv,
bytecode, .pytest_tmp*, dumps, dados sintéticos e logs brutos. Não apagar esses
arquivos para preparar a entrega. Arquivos novos não aparecem em git diff até
serem rastreados: abri-los diretamente, sem stage.

Comandos somente leitura para revisão:

```powershell
git status --short
git branch -vv
git diff --check
git diff --cached --check
git diff -- scripts/reconcile_storage.py tests/test_reconcile_storage_cli.py
git diff -- docs/supabase-deployment-runbook.md docs/storage-orphan-cleanup-strategy.md
git log --graph --oneline --decorate --all -20
```

Mensagem sugerida: `fix: exige inventário Storage completo e prepara backup e deploy seguro`.
Nenhum add, commit, push, merge, rebase ou deploy foi executado. O contêiner
descartável foi parado após as verificações finais, sem remover dados locais.
